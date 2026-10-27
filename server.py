#!/usr/bin/env python3
"""Монетка — локальный сервер: живые котировки (ЦБ РФ, Bybit), вклады и недвижимость.

Запуск:  python server.py   ->  http://127.0.0.1:8787
Только стандартная библиотека Python 3.10+. Для Авито и Циан нужен локальный Chrome.
"""
from __future__ import annotations

import base64
import gzip
import json
import math
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
BUNDLED_CACHE_DIR = os.path.join(ROOT, "data")
# На Vercel каталог проекта только для чтения — свежий кэш живёт в /tmp,
# а снимок data/*.json из репозитория используется как резерв.
CACHE_DIR = os.environ.get("MONETKA_CACHE_DIR") or ("/tmp/monetka" if os.environ.get("VERCEL") else BUNDLED_CACHE_DIR)
os.makedirs(CACHE_DIR, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 Monetka/1.0"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
MSK = timezone(timedelta(hours=3))
LOCK = threading.Lock()
MEM: dict[str, dict] = {}
PHOTOS_MEM: dict[str, dict] = {}

COINS = [
    ("bitcoin", "btc-bitcoin", "BTC", "Bitcoin"),
    ("ethereum", "eth-ethereum", "ETH", "Ethereum"),
    ("solana", "sol-solana", "SOL", "Solana"),
    ("binancecoin", "bnb-binance-coin", "BNB", "BNB"),
    ("ripple", "xrp-xrp", "XRP", "XRP"),
    ("cardano", "ada-cardano", "ADA", "Cardano"),
    ("dogecoin", "doge-dogecoin", "DOGE", "Dogecoin"),
    ("sui", "sui-sui", "SUI", "Sui"),
    ("tron", "trx-tron", "TRX", "TRON"),
    ("avalanche-2", "avax-avalanche", "AVAX", "Avalanche"),
    ("chainlink", "link-chainlink", "LINK", "Chainlink"),
    ("tether", "usdt-tether", "USDT", "Tether"),
]
METALS = {"1": ("XAU", "Золото"), "2": ("XAG", "Серебро"), "3": ("XPT", "Платина"), "4": ("XPD", "Палладий")}
FX_CODES = ["USD", "EUR", "CNY", "GBP", "CHF", "JPY", "TRY", "KZT", "BYN", "AED"]
FX_HISTORY_IDS = {"USD": "R01235", "EUR": "R01239", "CNY": "R01375", "GBP": "R01010"}
MOEX_FX = {
    "USDRUB_TOM": "USD",
    "EURRUB_TOM": "EUR",
    "CNYRUB_TOM": "CNY",
    "GBPRUB_TOM": "GBP",
    "CHFRUB_TOM": "CHF",
    "JPYRUB_TOM": "JPY",
    "TRYRUB_TOM": "TRY",
    "KZTRUB_TOM": "KZT",
    "BYNRUB_TOM": "BYN",
    "AEDRUB_TOM": "AED",
}
# Пары, которых нет на MOEX: EUR не торгуется с 2024 года, курс берём у Coinbase.
LIVE_FX_FALLBACK = ["USD", "EUR", "CNY", "GBP", "CHF", "JPY"]

SPB_DISTRICTS = (
    "адмиралтейский", "василеостровский", "выборгский", "калининский", "кировский",
    "колпинский", "красногвардейский", "красносельский", "кронштадтский", "курортный",
    "московский", "невский", "петроградский", "петродворцовый", "приморский",
    "пушкинский", "фрунзенский", "центральный",
)
REGION_CITIES = (
    "шлиссельбург", "всеволожск", "гатчина", "выборг", "сосновый бор", "тихвин",
    "кириши", "волхов", "луга", "кингисепп", "приозерск", "сертолово", "мурино",
    "кудрово", "бугры", "коммунар", "низино", "новогорелово", "токсово", "колтуши",
)


# ---------------------------------------------------------------- transport
def http_get(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*", "Accept-Language": "ru-RU,ru;q=0.9", "Accept-Encoding": "gzip, deflate"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        encoding = (resp.headers.get("Content-Encoding") or "").lower()
    if encoding == "gzip":
        body = gzip.decompress(body)
    elif encoding == "deflate":
        body = zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def http_text(url: str, encoding: str = "utf-8", timeout: int = 30) -> str:
    return http_get(url, timeout).decode(encoding, "replace")


def http_json(url: str, timeout: int = 30):
    return json.loads(http_get(url, timeout).decode("utf-8"))


# ---------------------------------------------------------------- headless browser
# Авито и Циан отдают антибот-заглушку обычному HTTP-клиенту. Локальный Chrome
# проходит JS-проверку, поэтому тянем готовый DOM через DevTools Protocol.
CHROME_CANDIDATES = (
    os.environ.get("CHROME_PATH"),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)
SCRAPE_LOCK = threading.Lock()


def chrome_path() -> str:
    for path in CHROME_CANDIDATES:
        if path and os.path.exists(path):
            return path
    raise RuntimeError("Chrome не найден: задайте CHROME_PATH или установите Google Chrome")


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise RuntimeError("WebSocket закрыт")
        buf += chunk
    return buf


def _ws_send(sock: socket.socket, text: str):
    data = text.encode("utf-8")
    head = bytearray([0x81])
    if len(data) < 126:
        head.append(0x80 | len(data))
    elif len(data) < 65536:
        head.append(0x80 | 126)
        head += struct.pack(">H", len(data))
    else:
        head.append(0x80 | 127)
        head += struct.pack(">Q", len(data))
    mask = os.urandom(4)
    head += mask
    sock.sendall(bytes(head) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))


def _ws_recv(sock: socket.socket):
    parts = []
    while True:
        first, second = _recv_exact(sock, 2)
        opcode = first & 0x0F
        size = second & 0x7F
        if size == 126:
            size = struct.unpack(">H", _recv_exact(sock, 2))[0]
        elif size == 127:
            size = struct.unpack(">Q", _recv_exact(sock, 8))[0]
        payload = _recv_exact(sock, size)
        if second & 0x80:  # Chrome не маскирует ответы, но на всякий случай
            mask = payload[:4]
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload[4:]))
        if opcode == 8:
            return None
        if opcode == 9:
            continue
        if opcode in (0, 1):
            parts.append(payload)
            if first & 0x80:
                return b"".join(parts).decode("utf-8", "replace")


def _ws_connect(url: str) -> socket.socket:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    sock = socket.create_connection((parsed.hostname, parsed.port), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    path = parsed.path + (("?" + parsed.query) if parsed.query else "")
    request = (
        f"GET {path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode())
    response = b""
    while b"\r\n\r\n" not in response:
        response += sock.recv(4096)
    if b" 101 " not in response.split(b"\r\n", 1)[0]:
        raise RuntimeError("Chrome отклонил WebSocket-подключение")
    return sock


def _cdp_call(sock: socket.socket, msg_id: int, method: str, params: dict | None = None):
    _ws_send(sock, json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    while True:
        message = _ws_recv(sock)
        if message is None:
            raise RuntimeError("Chrome закрыл соединение")
        data = json.loads(message)
        if data.get("id") == msg_id:
            return data


def browser_json_many(urls, expression: str, waits, stealth: bool = False):
    """Открывает несколько URL в одном Chrome и возвращает JSON с каждой страницы."""
    if os.environ.get("VERCEL"):
        raise RuntimeError("Авито/Циан недоступны на Vercel: нужен локальный Chrome")
    chrome = chrome_path()
    with SCRAPE_LOCK:
        profile = tempfile.mkdtemp(prefix="monetka-chrome-")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        args = [
            chrome, "--headless=new", "--disable-gpu", "--no-first-run",
            "--no-default-browser-check", "--window-size=1400,1000",
            f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "about:blank",
        ]
        if stealth:
            # Банки отсекают headless-браузер по UA и AutomationControlled.
            args += ["--disable-blink-features=AutomationControlled", f"--user-agent={BROWSER_UA}"]
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags,
        )
        try:
            target = None
            deadline = time.time() + 25
            while time.time() < deadline:
                try:
                    tabs = json.loads(http_get(f"http://127.0.0.1:{port}/json/list", timeout=3))
                    target = next((tab for tab in tabs if tab.get("type") == "page"), None)
                    if target:
                        break
                except Exception:
                    time.sleep(0.4)
            if not target:
                raise RuntimeError("Chrome не запустился")
            sock = _ws_connect(target["webSocketDebuggerUrl"])
            values = []
            try:
                _cdp_call(sock, 1, "Page.enable")
                msg_id = 2
                for index, (url, wait) in enumerate(zip(urls, waits)):
                    _cdp_call(sock, msg_id, "Page.navigate", {"url": url})
                    msg_id += 1
                    time.sleep(wait)
                    result = _cdp_call(sock, msg_id, "Runtime.evaluate", {"expression": expression, "returnByValue": True})
                    msg_id += 1
                    if result.get("result", {}).get("exceptionDetails"):
                        raise RuntimeError("Chrome JS: " + str(result["result"]["exceptionDetails"])[:200])
                    value = result.get("result", {}).get("result", {}).get("value")
                    if not isinstance(value, str):
                        raise RuntimeError("Chrome не вернул данные страницы")
                    parsed = json.loads(value)
                    values.append(parsed)
                    if index and isinstance(parsed, list) and not parsed:
                        break
            finally:
                sock.close()
            return values
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=6)
            except subprocess.TimeoutExpired:
                proc.kill()
            shutil.rmtree(profile, ignore_errors=True)


def browser_json(url: str, expression: str, wait: float = 11):
    """Открывает url в headless Chrome и возвращает JSON из expression."""
    return browser_json_many([url], expression, [wait])[0]


def _page_url(url: str, page: int) -> str:
    if page <= 1:
        return url
    return url + ("&" if "?" in url else "?") + f"p={page}"


def browser_json_pages(url: str, expression: str, pages: int, first_wait: float = 10, wait: float = 5):
    """Собирает JSON с нескольких страниц выдачи, пока страница не опустеет."""
    urls = [_page_url(url, page) for page in range(1, pages + 1)]
    values = browser_json_many(urls, expression, [first_wait] + [wait] * (pages - 1))
    rows = []
    for value in values:
        if isinstance(value, list):
            rows.extend(value)
    return rows


def _digits(value) -> int:
    return int(re.sub(r"\D", "", str(value or "")) or 0)



# ---------------------------------------------------------------- cache
def now_msk() -> str:
    return datetime.now(MSK).isoformat(timespec="seconds")


def _snapshot(name: str):
    path = os.path.join(BUNDLED_CACHE_DIR, name + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("value") is not None:
            meta = dict(cached.get("meta") or {})
            meta["stale"] = True
            return cached["value"], meta
    except Exception:
        pass
    return None


def source(name: str, ttl: int, builder, force: bool = False):
    """Fetch with TTL cache and last-known-good fallback on disk."""
    # shortcut: на Vercel холодный live-сбор медленных источников не влезает в лимит функции,
    # поэтому отдаём снапшот из data/. Для live-сбора задайте MONETKA_LIVE=1.
    if not force and os.environ.get("VERCEL") and not os.environ.get("MONETKA_LIVE"):
        snap = _snapshot(name)
        if snap:
            return snap

    if not force:
        hit = MEM.get(name)
        if hit and hit["exp"] > time.time():
            return hit["value"], hit["meta"]

        path = os.path.join(CACHE_DIR, name + ".json")
        try:
            age = time.time() - os.path.getmtime(path)
            if age < ttl:
                with open(path, encoding="utf-8") as f:
                    cached = json.load(f)
                if cached.get("value") is not None:
                    meta = cached.get("meta") or {"ok": True, "updated": None, "stale": False}
                    with LOCK:
                        MEM[name] = {"exp": time.time() + ttl - age, "value": cached["value"], "meta": meta}
                    return cached["value"], meta
        except Exception:
            pass

    try:
        value = builder()
        meta = {"ok": True, "updated": now_msk(), "stale": False}
        with LOCK:
            MEM[name] = {"exp": time.time() + ttl, "value": value, "meta": meta}
        try:
            path = os.path.join(CACHE_DIR, name + ".json")
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"value": value, "meta": meta}, f, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError:
            pass
        return value, meta
    except Exception as exc:  # noqa: BLE001 - любая сетевая ошибка -> кэш
        cached = None
        for directory in (CACHE_DIR, BUNDLED_CACHE_DIR):
            path = os.path.join(directory, name + ".json")
            if not os.path.exists(path):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    cached = json.load(f)
                break
            except Exception:
                cached = None
        meta = {
            "ok": False,
            "error": str(exc)[:300],
            "stale": cached is not None,
            "updated": (cached or {}).get("meta", {}).get("updated"),
        }
        with LOCK:
            MEM[name] = {"exp": time.time() + 30, "value": (cached or {}).get("value"), "meta": meta}
        if cached is None:
            raise RuntimeError(f"{name}: {exc}") from exc
        return cached["value"], meta


# ---------------------------------------------------------------- crypto (Bybit)
BYBIT = "https://api.bybit.com"
BYBIT_SPOT_PAIR = {"USDT": "USDCUSDT"}  # у USDT нет пары к самому себе


def _bybit_tickers() -> dict:
    data = http_json(f"{BYBIT}/v5/market/tickers?category=spot", timeout=25)
    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit: {data.get('retMsg')}")
    return {row["symbol"]: row for row in data.get("result", {}).get("list", [])}


def _bybit_spark(pair: str, inverse: bool = False) -> list:
    try:
        data = http_json(
            f"{BYBIT}/v5/market/kline?category=spot&symbol={pair}&interval=60&limit=168", timeout=20
        )
        closes = [float(row[4]) for row in reversed(data["result"]["list"])]
        if inverse:
            closes = [1 / p for p in closes if p]
        return [round(p, 8) for p in closes[::3]][-60:]
    except Exception:
        return []


def build_crypto():
    tickers = _bybit_tickers()

    def one(coin):
        cg_id, pp_id, sym, name = coin
        pair = BYBIT_SPOT_PAIR.get(sym, sym + "USDT")
        row = tickers.get(pair)
        if not row:
            return None
        price = float(row["lastPrice"])
        # Для USDT берём USDC/USDT и переворачиваем: получаем USD за 1 USDT.
        inverse = sym == "USDT"
        if inverse and price:
            price = 1 / price
        change = float(row.get("price24hPcnt") or 0) * 100
        if inverse:
            change = -change
        return {
            "id": cg_id,
            "symbol": sym,
            "name": name,
            "price": price,
            "change24h": change,
            "marketCap": None,
            "volume": float(row.get("turnover24h") or 0),
            "spark": _bybit_spark(pair, inverse),
            "tradeUrl": "https://www.bybit.com/fiat/trade/onramp" if sym == "USDT" else f"https://www.bybit.com/trade/spot/{sym}/USDT",
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        items = [item for item in pool.map(one, COINS) if item]
    if not items:
        raise RuntimeError("Bybit не вернул ни одной пары")
    return {"items": items, "provider": "Bybit"}


def build_crypto_fallback():
    """CoinPaprika — резервный источник, если Bybit недоступен."""

    def one(coin):
        cg_id, pp_id, sym, name = coin
        data = http_json(f"https://api.coinpaprika.com/v1/tickers/{pp_id}", timeout=20)
        usd = data["quotes"]["USD"]
        return {
            "id": cg_id,
            "symbol": sym,
            "name": name,
            "price": float(usd["price"]),
            "change24h": usd.get("percent_change_24h"),
            "marketCap": usd.get("market_cap"),
            "volume": usd.get("volume_24h"),
            "spark": [],
            "tradeUrl": "https://www.bybit.com/fiat/trade/onramp" if sym == "USDT" else f"https://www.bybit.com/trade/spot/{sym}/USDT",
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        items = list(pool.map(one, COINS))
    return {"items": items, "provider": "CoinPaprika"}


# ---------------------------------------------------------------- metals (ЦБ РФ)
def build_metals():
    today = datetime.now(MSK).date()
    start = today - timedelta(days=40)
    url = (
        "https://www.cbr.ru/scripts/xml_metall.asp"
        f"?date_req1={start:%d/%m/%Y}&date_req2={today:%d/%m/%Y}"
    )
    xml = http_text(url, "cp1251")
    records = re.findall(
        r'<Record Date="([\d.]+)" Code="(\d)">\s*<Buy>([\d.,]+)</Buy>', xml
    )
    if not records:
        raise RuntimeError("ЦБ РФ не вернул котировки металлов")

    series: dict[str, list] = {code: [] for code in METALS}
    for d, code, val in records:
        if code in series:
            series[code].append({"d": d, "v": float(val.replace(",", "."))})
    for rows in series.values():
        rows.sort(key=lambda r: datetime.strptime(r["d"], "%d.%m.%Y"))

    items = []
    for code, (ticker, name) in METALS.items():
        rows = series[code]
        if not rows:
            continue
        last = rows[-1]
        prev = rows[-2]["v"] if len(rows) > 1 else last["v"]
        items.append(
            {
                "id": ticker,
                "code": ticker,
                "name": name,
                "price": last["v"],          # ₽ за грамм
                "prev": prev,
                "change24h": (last["v"] / prev - 1) * 100 if prev else 0,
                "date": last["d"],
                "spark": [round(r["v"], 2) for r in rows[-30:]],
            }
        )
    if not items:
        raise RuntimeError("Нет данных по металлам")
    return {"items": items, "provider": "ЦБ РФ"}


# ---------------------------------------------------------------- fx (ЦБ РФ)
def build_fx():
    try:
        data = http_json("https://www.cbr-xml-daily.ru/daily_json.js", timeout=8)
        vals, d = data["Valute"], data["Date"][:10]
    except Exception:
        xml = http_text("https://www.cbr.ru/scripts/XML_daily.asp", "cp1251", timeout=8)
        d = datetime.now(MSK).strftime("%Y-%m-%d")
        vals = {}
        for block in re.findall(r"<Valute\b.*?</Valute>", xml, re.S):
            code = re.search(r"<CharCode>(\w+)</CharCode>", block)
            if not code:
                continue
            nom = float(re.search(r"<Nominal>([\d.]+)</Nominal>", block).group(1))
            val = float(re.search(r"<Value>([\d,]+)</Value>", block).group(1).replace(",", "."))
            prev = re.search(r"<Previous>([\d,]+)</Previous>", block)
            vals[code.group(1)] = {
                "Nominal": nom,
                "Value": val,
                "Previous": float(prev.group(1).replace(",", ".")) if prev else val,
            }

    items = []
    for code in FX_CODES:
        v = vals.get(code)
        if not v:
            continue
        nominal = float(v.get("Nominal") or 1)
        value = float(v["Value"]) / nominal
        prev = float(v.get("Previous") or v["Value"]) / nominal
        items.append(
            {
                "code": code,
                "name": v.get("Name") if isinstance(v.get("Name"), str) else code,
                "value": value,
                "prev": prev,
                "nominal": nominal,
                "change24h": (value / prev - 1) * 100 if prev else 0,
            }
        )
    live = build_fx_live()
    for item in items:
        item["live"] = live.get(item["code"])
    live_updated = max((rate["updated"] for rate in live.values() if rate.get("updated")), default=None)
    if not items:
        raise RuntimeError("Нет курсов ЦБ РФ")
    return {"items": items, "date": d, "provider": "ЦБ РФ", "liveUpdated": live_updated}


def _moex_iso(value):
    match = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", str(value or ""))
    return f"{match.group(1)}T{match.group(2)}+03:00" if match else None


def _parse_moex_rates(payload):
    securities = payload.get("securities") or {}
    marketdata = payload.get("marketdata") or {}
    scols, mcols = securities.get("columns") or [], marketdata.get("columns") or []
    if not scols or not mcols:
        return {}
    si = {name: index for index, name in enumerate(scols)}
    mi = {name: index for index, name in enumerate(mcols)}
    names, previous, face = {}, {}, {}
    for row in securities.get("data") or []:
        secid = row[si["SECID"]]
        names[secid] = row[si["SHORTNAME"]]
        if "PREVPRICE" in si and row[si["PREVPRICE"]] is not None:
            previous[secid] = row[si["PREVPRICE"]]
        if "FACEVALUE" in si and row[si["FACEVALUE"]] is not None:
            face[secid] = row[si["FACEVALUE"]]

    rates = {}
    for row in marketdata.get("data") or []:
        secid = row[mi["SECID"]]
        code = MOEX_FX.get(names.get(secid))
        if not code:
            continue
        last = row[mi["LAST"]] if "LAST" in mi else None
        price = last or row[mi["MARKETPRICE"]] or row[mi["WAPRICE"]]
        if not price:
            continue
        updated = _moex_iso(row[mi["SYSTIME"]]) if "SYSTIME" in mi else None
        if updated and code in rates and rates[code]["updated"] and updated < rates[code]["updated"]:
            continue
        nominal = float(face.get(secid) or 1)
        value = float(price) / nominal
        prev = previous.get(secid)
        prev = float(prev) / nominal if prev else None
        rates[code] = {
            "value": value,
            "prev": prev,
            "change24h": (value / prev - 1) * 100 if last and prev else None,
            "updated": updated,
            "source": "MOEX",
            "traded": bool(last),
        }
    return rates


def _coinbase_rate(code):
    # MOEX не торгует EUR с 2024 года, Yahoo из РФ недоступен.
    data = http_json(
        f"https://api.coinbase.com/v2/exchange-rates?currency={code}",
        timeout=8,
    )
    price = ((data.get("data") or {}).get("rates") or {}).get("RUB")
    if not price:
        return None
    return {
        "value": float(price),
        "prev": None,
        "change24h": None,
        "updated": now_msk(),
        "source": "Coinbase",
    }


def _fetch_many(fn, codes):
    if not codes:
        return {}
    found = {}
    with ThreadPoolExecutor(max_workers=min(6, len(codes))) as pool:
        futures = {pool.submit(fn, code): code for code in codes}
        for future in as_completed(futures):
            try:
                rate = future.result()
            except Exception:
                continue
            if rate:
                found[futures[future]] = rate
    return found


def build_fx_live():
    rates = {}
    try:
        payload = http_json(
            "https://iss.moex.com/iss/engines/currency/markets/selt/securities.json"
            "?iss.meta=off&iss.only=securities,marketdata",
            timeout=8,
        )
        rates = _parse_moex_rates(payload)
    except Exception:
        pass
    for code in [code for code, rate in rates.items() if not rate.get("traded")]:
        rates.pop(code, None)
    rates.update(_fetch_many(_coinbase_rate, [code for code in LIVE_FX_FALLBACK if code not in rates]))
    for rate in rates.values():
        rate.pop("traded", None)
    return rates


def _fx_history_points(code, days=365):
    cbr_id = FX_HISTORY_IDS.get(code)
    if not cbr_id:
        return []
    today = datetime.now(MSK).date()
    start = today - timedelta(days=days)
    url = (
        "https://www.cbr.ru/scripts/XML_dynamic.asp"
        f"?date_req1={start:%d/%m/%Y}&date_req2={today:%d/%m/%Y}&VAL_NM_RQ={cbr_id}"
    )
    try:
        xml = http_text(url, "cp1251", timeout=20)
    except Exception:
        return []
    records = re.findall(
        r'<Record Date="([\d.]+)"[^>]*>\s*<Nominal>([\d.]+)</Nominal>\s*<Value>([\d,]+)</Value>',
        xml,
    )
    points = []
    for date_text, nominal, value in records:
        try:
            number = float(value.replace(",", ".")) / float(nominal)
            stamp = datetime.strptime(date_text, "%d.%m.%Y").date().isoformat()
        except (TypeError, ValueError):
            continue
        if number > 0:
            points.append({"t": stamp, "c": round(number, 4)})
    points.sort(key=lambda point: point["t"])
    return points


def _fx_history(code):
    return [point["c"] for point in _fx_history_points(code, 45)][-30:]


HISTORY_DAYS = {"1d": 1, "7d": 7, "1m": 30, "3m": 90, "1y": 365, "all": 730}


def _range_days(range_name):
    return HISTORY_DAYS.get(range_name, 30)


def _bybit_history(symbol, range_name):
    pair = BYBIT_SPOT_PAIR.get(symbol, symbol + "USDT")
    inverse = symbol == "USDT"
    if range_name in ("1d", "7d"):
        interval = "60"
        limit = 24 if range_name == "1d" else 168
    else:
        interval = "D"
        limit = {"1m": 30, "3m": 90, "1y": 365, "all": 1000}.get(range_name, 30)
    data = http_json(
        f"{BYBIT}/v5/market/kline?category=spot&symbol={pair}&interval={interval}&limit={limit}",
        timeout=20,
    )
    rows = list(reversed(data["result"]["list"]))
    points = []
    for row in rows:
        try:
            stamp = datetime.fromtimestamp(int(row[0]) / 1000, MSK).isoformat(timespec="seconds")
            close = float(row[4])
        except (TypeError, ValueError, IndexError):
            continue
        if inverse and close:
            close = 1 / close
        points.append({"t": stamp, "c": round(close, 8)})
    return points


def _coingecko_history(cg_id, range_name):
    days = {"1d": 1, "7d": 7, "1m": 30, "3m": 90, "1y": 365, "all": 365}.get(range_name, 30)
    data = http_json(
        f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
        f"?vs_currency=usd&days={days}&interval=daily",
        timeout=25,
    )
    points = []
    for stamp, close in data.get("prices") or []:
        try:
            date = datetime.fromtimestamp(float(stamp) / 1000, MSK).isoformat(timespec="seconds")
            price = float(close)
        except (TypeError, ValueError):
            continue
        if price > 0:
            points.append({"t": date, "c": round(price, 8)})
    return points


def _crypto_history(cg_id, symbol, range_name):
    try:
        points = _bybit_history(symbol, range_name)
    except Exception:
        points = []
    if not points:
        try:
            points = _coingecko_history(cg_id, range_name)
        except Exception:
            points = []
    return points


HISTORY_DIR = os.path.join(BUNDLED_CACHE_DIR, "history")


def _history_snapshot(kind, asset_id):
    path = os.path.join(HISTORY_DIR, f"{kind}_{asset_id}.json")
    try:
        with open(path, encoding="utf-8") as handle:
            points = json.load(handle).get("points") or []
    except Exception:
        return []
    return points


def _slice_history(points, range_name):
    if not points or range_name == "all":
        return points
    days = max(_range_days(range_name), 2)
    cutoff = datetime.now(MSK).date() - timedelta(days=days)
    filtered = []
    for point in points:
        try:
            stamp = datetime.strptime(str(point.get("t") or "")[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
        if stamp >= cutoff:
            filtered.append(point)
    return filtered or points[-days:]


def _history_points(kind, asset_id, range_name):
    snapshot_first = os.environ.get("VERCEL") and not os.environ.get("MONETKA_LIVE")
    if snapshot_first:
        points = _history_snapshot(kind, asset_id)
        if points:
            return _slice_history(points, range_name), "snapshot"
    try:
        if kind == "crypto":
            coin = next((item for item in COINS if item[0] == asset_id), None)
            points = _crypto_history(coin[0], coin[2], range_name) if coin else []
        elif kind == "metal":
            points = _metal_history(asset_id, range_name)
        else:
            points = _fx_history_points(asset_id, _range_days(range_name))
    except Exception:
        points = []
    if points:
        return points, "live"
    points = _history_snapshot(kind, asset_id)
    if points:
        return _slice_history(points, range_name), "snapshot"
    return [], "none"


def _metal_history(asset_id, range_name):
    cbr_code = next((code for code, (ticker, _) in METALS.items() if ticker == asset_id), None)
    if not cbr_code:
        return []
    window = _range_days(range_name)
    fetch_days = max(window, 30)
    today = datetime.now(MSK).date()
    start = today - timedelta(days=fetch_days)
    url = (
        "https://www.cbr.ru/scripts/xml_metall.asp"
        f"?date_req1={start:%d/%m/%Y}&date_req2={today:%d/%m/%Y}"
    )
    xml = http_text(url, "cp1251", timeout=30)
    records = re.findall(
        r'<Record Date="([\d.]+)" Code="(\d)">\s*<Buy>([\d.,]+)</Buy>',
        xml,
    )
    points = []
    for date_text, code, value in records:
        if code != cbr_code:
            continue
        try:
            stamp = datetime.strptime(date_text, "%d.%m.%Y").date().isoformat()
            price = float(value.replace(",", "."))
        except (TypeError, ValueError):
            continue
        points.append({"t": stamp, "c": round(price, 2)})
    points.sort(key=lambda point: point["t"])
    return points[-max(window, 2):] if window < 30 else points[-window:]


def api_history(params):
    kind = str((params or {}).get("kind") or "").strip()
    asset_id = str((params or {}).get("id") or "").strip()
    range_name = str((params or {}).get("range") or "1m").strip()
    if range_name not in HISTORY_DAYS:
        raise ValueError("Неизвестный диапазон")
    if kind == "crypto":
        coin = next((item for item in COINS if item[0] == asset_id), None)
        if not coin:
            raise ValueError("Актив не найден")
        _, _, symbol, name = coin
        unit, base_source = "USD", "Bybit / CoinGecko"
    elif kind == "metal":
        metal = next(((ticker, title) for code, (ticker, title) in METALS.items() if ticker == asset_id), None)
        if not metal:
            raise ValueError("Актив не найден")
        symbol, name = metal
        unit, base_source = "RUB/g", "ЦБ РФ"
    elif kind == "fx":
        if asset_id not in FX_HISTORY_IDS:
            raise ValueError("История доступна для USD, EUR, CNY и GBP")
        symbol = name = asset_id
        unit, base_source = "RUB", "ЦБ РФ"
    else:
        raise ValueError("Неизвестный тип актива")
    points, used = _history_points(kind, asset_id, range_name)
    if not points:
        raise RuntimeError("История временно недоступна. Попробуйте позже.")
    return {
        "kind": kind,
        "id": asset_id,
        "name": name,
        "symbol": symbol,
        "unit": unit,
        "range": range_name,
        "source": base_source if used == "live" else "снимок",
        "points": points,
    }


# ---------------------------------------------------------------- key rate
def build_key_rate():
    url = "https://www.cbr.ru/hd_base/KeyRate/"
    html = http_text(url)
    m = re.search(r'<table[^>]*class="data"[^>]*>(.*?)</table>', html, re.S)
    if not m:
        raise RuntimeError("Не найдена таблица ключевой ставки")
    row = re.search(r"<td>(\d{2}\.\d{2}\.\d{4})</td>\s*<td>([\d,]+)</td>", m.group(1))
    if not row:
        raise RuntimeError("Не найдена ключевая ставка")
    return {"value": float(row.group(2).replace(",", ".")), "date": row.group(1)}


# ---------------------------------------------------------------- deposits (только сайты банков)
def _num(value):
    if value is None:
        return None
    try:
        return float(str(value).replace("\xa0", "").replace(" ", "").replace(",", ".").replace("%", ""))
    except ValueError:
        m = re.search(r"\d+(?:[.,]\d+)?", str(value))
        return float(m.group().replace(",", ".")) if m else None


def parse_term_days(name: str):
    n = re.search(r"(\d+)\s*(?:дн|день|дней)", name, re.I)
    if n:
        return int(n.group(1))
    m = re.search(r"(\d+)\s*мес", name, re.I)
    if m:
        return int(m.group(1)) * 30
    tail = re.search(r"\b(\d{2,4})\s*$", name)
    if tail and 30 <= int(tail.group(1)) <= 1100:
        return int(tail.group(1))
    return None


def _clean(text: str) -> str:
    import html as html_mod
    return re.sub(r"\s+", " ", html_mod.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def _deposit_ok(rate) -> bool:
    return bool(rate) and 0 < rate <= 40


def _direct_term(text):
    value = _clean(text).strip(" ,.")
    return (value.replace("месяцев", "мес.").replace("месяца", "мес.")
            .replace("месяц", "мес.").replace("года", "г.").replace("год", "г.").replace("лет", "г."))


def _direct_term_days(text):
    return None if re.search(r"[-–—]", text or "") else parse_term_days(text)


def _parse_vtb_deposits(html):
    rows, seen = [], set()
    for chunk in html.split("card-layout-gridstyles__Item-chips")[1:]:
        link = re.search(r'<a[^>]*class="[^"]*TitleLinkWrapper[^"]*"[^>]*>(.*?)</a>', chunk, re.S)
        if not link:
            continue
        name = _clean(link.group(1))
        href = re.search(r'href="([^"]+)"', link.group(0))
        text = _clean(chunk)
        rates = re.findall(r"(?:До\s*)?([\d]+(?:[.,]\d+)?)\s*%\s*(Доходность|Ставка), годовых", text)
        rate = next((_num(value) for value, label in rates if label == "Ставка"), None)
        if rate is None and rates:
            rate = _num(rates[0][0])
        min_match = re.search(r"От\s*([\d\s]+)\s*₽", text)
        if not name or name in seen or not _deposit_ok(rate) or not min_match:
            continue
        term = ""
        term_match = re.search(r"([^А-Яа-я]{0,15}\d[\d\s,.:-]*\s*(?:мес|год|лет|дн)[^А-Яа-я]{0,10})\s*(?:Срок|Период)", text)
        if term_match:
            term = _direct_term(term_match.group(1))
        elif "Бессрочно" in text:
            term = "бессрочно"
        seen.add(name)
        rows.append((name, rate, _num(min_match.group(1)), term, "https://www.vtb.ru" + href.group(1) if href else "https://www.vtb.ru/personal/vklady-i-scheta/"))
    return rows


def _parse_gazprom_deposits(html):
    text = _clean(html)
    start = text.find("Вклад года")
    if start < 0:
        start = text.find("Все вклады")
    text = text[max(0, start):]
    pattern = re.compile(r"Вклад «([^»]+)»\s+Вклад «[^»]+»\s+.*?\s+до\s+([\d]+(?:[.,]\d+)?)% годовых\s+от\s+([\d\s,.]+)\s*(тыс\.?|млн)?\s*₽,\s*(?:от|на)\s+([^,]+?)\s+(?:Открыть|Подробнее)")
    rows, seen = [], set()
    for match in pattern.finditer(text):
        name, rate, amount, unit, term = match.groups()
        if name in seen:
            continue
        multiplier = 1000 if unit and unit.startswith("тыс") else 1000000 if unit and unit.startswith("млн") else 1
        seen.add(name)
        rows.append((name, _num(rate), (_num(amount) or 0) * multiplier, _direct_term(term), "https://www.gazprombank.ru/personal/deposits/"))
    return rows


def _parse_rshb_deposits(html):
    text = _clean(html)
    start = text.find("Вклады и накопительные счета")
    end = text.find("Другие вклады и счета", max(0, start))
    text = text[start:end] if start >= 0 and end > start else text
    names = list(re.finditer(r"(Вклад «[^»]+»|Социальный банковский вклад|Накопительный счёт «[^»]+»)", text))
    rows, seen = [], set()
    for index, match in enumerate(names):
        name = match.group(1)
        if name in seen:
            continue
        chunk = text[match.end():names[index + 1].start() if index + 1 < len(names) else len(text)]
        rate = re.search(r"До\s*([\d]+(?:[.,]\d+)?)%\s*(?:ставка|ставка по)", chunk)
        term = re.search(r"([^А-Яа-я]{0,15}(?:\d[\d\s,.-]*(?:мес|год|лет|дн)[^А-Яа-я]{0,10})|Бессрочно)\s*срок", chunk)
        min_match = re.search(r"От\s*([\d\s,.]+)\s*(тыс\.?|млн)?\s*₽", chunk)
        if not rate or not min_match:
            continue
        multiplier = 1000 if min_match.group(2) and min_match.group(2).startswith("тыс") else 1000000 if min_match.group(2) and min_match.group(2).startswith("млн") else 1
        seen.add(name)
        rows.append((name, _num(rate.group(1)), (_num(min_match.group(1)) or 0) * multiplier, _direct_term(term.group(1)) if term else "", "https://www.rshb.ru/natural/deposits/"))
    return rows


def _parse_tbank_deposits(html):
    text = _clean(html.replace("&nbsp;", " "))
    if "Вклад со ставкой" not in text:
        text = _clean(html)
    rows = []
    rate = re.search(r"Вклад со\s*ставкой до\s*([\d]+(?:[.,]\d+)?)%", text)
    min_match = re.search(r"От\s*([\d]+)\s*до\s*([\d]+)\s*месяцев,\s*от\s*([\d\s]+)\s*₽", text)
    if rate and min_match:
        rows.append(("Вклад", _num(rate.group(1)), _num(min_match.group(3)), f"от {min_match.group(1)} до {min_match.group(2)} мес.", "https://www.tbank.ru/deposits/"))
    saving = re.search(r"Накопительный счет со\s*ставкой до\s*([\d]+(?:[.,]\d+)?)%", text)
    if saving:
        rows.append(("Накопительный счёт", _num(saving.group(1)), 1, "бессрочно", "https://www.tbank.ru/deposits/"))
    if not rows:
        # Промо-лендинг («Хоккейный вклад») отдаёт ставку и сумму отдельными строками.
        rate = re.search(r"Ставка до\s*([\d]+(?:[.,]\d+)?)\s*%", text)
        min_match = re.search(r"Минимальная сумма\s*[—–-]\s*([\d\s]+)\s*₽", text)
        if rate and min_match:
            rows.append(("Вклад", _num(rate.group(1)), _num(min_match.group(1)), "", "https://www.tbank.ru/deposits/"))
    return rows


def _parse_domrf_deposits(html):
    text = _clean(html)
    rate = re.search(r"Ставка до ([\d]+(?:[.,]\d+)?)%", text)
    min_match = re.search(r"Сумма от ([\d\s]+)\s*₽", text)
    term = re.search(r"Срок от (.+?)\s+до\s+(.+?)(?=\s+[А-ЯЁ]|$)", text)
    if not rate or not min_match:
        return []
    term_text = f"от {_direct_term(term.group(1))} до {_direct_term(term.group(2))}" if term else ""
    return [("Мой Дом", _num(rate.group(1)), _num(min_match.group(1)), term_text, "https://domrfbank.ru/deposits/")]


def _is_alfa_deposit(line):
    return line == "Социальный вклад" or (line.startswith("Альфа") and "Вклад" in line)


def _is_otp_deposit(line):
    return line.startswith("Вклад «")


def _parse_rendered_deposits(text, is_name, link):
    """Разбирает видимый текст страницы банка: карточки идут строками."""
    text = re.sub(r"[\u00a0\u2009\u202f]", " ", text or "")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    starts = [index for index, line in enumerate(lines) if is_name(line)]
    rows = []
    for position, start in enumerate(starts):
        chunk = lines[start:starts[position + 1] if position + 1 < len(starts) else len(lines)]
        rate = next(
            (
                _num(match.group(1))
                for line in chunk
                if (match := re.match(r"^(?:До\s*)?(\d+(?:[.,]\d+)?)\s*%\s*(?:годовых)?$", line))
            ),
            None,
        )
        if not _deposit_ok(rate):
            continue
        amount = next(
            (_num(match.group(1)) for line in chunk if (match := re.match(r"^От\s+([\d\s]+)\s*₽$", line))),
            None,
        )
        term = next(
            (chunk[index] for index in range(len(chunk) - 1) if chunk[index + 1] in ("срок", "Срок оформления")),
            "",
        )
        rows.append((chunk[0], rate, amount, _direct_term(term), link))
    return rows


def _parse_alfa_deposits(text):
    return _parse_rendered_deposits(text, _is_alfa_deposit, "https://alfabank.ru/make-money/deposits/")


def _parse_otp_deposits(text):
    return _parse_rendered_deposits(text, _is_otp_deposit, "https://www.otpbank.ru/retail/deposit/")


DIRECT_BANKS = [
    ("vtb", "ВТБ", "https://www.vtb.ru/personal/vklady-i-scheta/", _parse_vtb_deposits),
    ("gazprom", "Газпромбанк", "https://www.gazprombank.ru/personal/deposits/", _parse_gazprom_deposits),
    ("rshb", "Россельхозбанк", "https://www.rshb.ru/natural/deposits/", _parse_rshb_deposits),
    ("tbank", "Т-Банк", "https://www.tbank.ru/deposits/", _parse_tbank_deposits),
    ("domrf", "Банк ДОМ.РФ", "https://domrfbank.ru/deposits/", _parse_domrf_deposits),
    ("alfa", "Альфа-Банк", "https://alfabank.ru/make-money/deposits/", _parse_alfa_deposits),
    ("otp", "ОТП Банк", "https://www.otpbank.ru/retail/deposit/", _parse_otp_deposits),
]

# Ставки этих банков видны только после выполнения JS, поэтому тянем DOM через Chrome.
BROWSER_BANK_KEYS = {"alfa", "otp", "tbank"}

DIRECT_BANK_LOGOS = {
    "vtb": "/logos/vtb.svg",
    "gazprom": "/logos/gazprombank.svg",
    "rshb": "/logos/rshb.svg",
    "tbank": "/logos/tbank.svg",
    "domrf": "/logos/domrf.png",
    "alfa": "/logos/alfa.ico",
    "otp": "/logos/otp.png",
}


def _render_deposit_pages(keys):
    urls = {key: url for key, bank, url, parser in DIRECT_BANKS if key in keys}
    pages = browser_json_many(
        [urls[key] for key in keys],
        "JSON.stringify(document.body.innerText)",
        [10] * len(keys),
        stealth=True,
    )
    return dict(zip(keys, pages))


def build_direct_banks():
    items, errors = [], []
    browser_keys = [key for key, *_ in DIRECT_BANKS if key in BROWSER_BANK_KEYS]
    rendered = {}
    if browser_keys and not os.environ.get("VERCEL"):
        try:
            rendered = _render_deposit_pages(browser_keys)
        except Exception as exc:  # noqa: BLE001 - без браузера просто меньше банков
            errors.append(f"браузер: {exc}")
    for key, bank, url, parser in DIRECT_BANKS:
        try:
            if key in BROWSER_BANK_KEYS:
                if not rendered.get(key):
                    raise RuntimeError("нужен локальный Chrome")
                rows = parser(rendered[key])
            else:
                rows = parser(http_text(url, timeout=45))
        except Exception as exc:  # noqa: BLE001 - один банк не должен ронять выдачу
            errors.append(f"{bank}: {exc}")
            continue
        for index, (name, rate, min_amount, term_text, link) in enumerate(rows):
            if not _deposit_ok(rate):
                continue
            min_amount = None if min_amount is not None and min_amount < 1 else min_amount
            items.append({
                "id": f"direct:{key}:{index}",
                "source": "direct",
                "sourceName": bank,
                "name": name,
                "bank": bank,
                "url": link,
                "logo": DIRECT_BANK_LOGOS.get(key, ""),
                "rate": float(rate),
                "rateMin": None,
                "apr": float(rate),
                "min": min_amount,
                "max": None,
                "currency": "RUB",
                "termDays": _direct_term_days(term_text),
                "termText": term_text,
                "note": "",
            })
    if not items:
        raise RuntimeError("Прямые сайты банков: " + ("; ".join(errors) or "нет данных"))
    return items


DEPOSIT_TTL = 10800


# ---------------------------------------------------------------- api
def _fx_block(fx, meta):
    return {
        "items": (fx or {}).get("items", []),
        "date": (fx or {}).get("date"),
        "liveUpdated": (fx or {}).get("liveUpdated"),
        "meta": meta,
    }


def api_market(force: bool = False, fx_only: bool = False):
    if fx_only:
        fx, fx_meta = source("fx", 900, build_fx, force=force)
        return {"fx": _fx_block(fx, fx_meta), "serverTime": now_msk()}

    with ThreadPoolExecutor(max_workers=4) as pool:
        crypto_future = pool.submit(source, "crypto", 3600, build_crypto, force)
        metals_future = pool.submit(source, "metals", 3600, build_metals, force)
        fx_future = pool.submit(source, "fx", 900, build_fx, force)
        key_future = pool.submit(source, "key_rate", 21600, build_key_rate)
        crypto, crypto_meta = crypto_future.result()
        metals, metals_meta = metals_future.result()
        fx, fx_meta = fx_future.result()
        key_rate, key_meta = key_future.result()

    if crypto_meta.get("ok") is False:
        try:
            fallback, fb_meta = source("crypto_fallback", 3600, build_crypto_fallback, force=force)
            crypto, crypto_meta = fallback, dict(fb_meta, note="Bybit недоступен, используются данные CoinPaprika")
        except Exception:
            pass

    usd = next((i["value"] for i in (fx or {}).get("items", []) if i["code"] == "USD"), None)
    if metals and usd:
        for item in metals["items"]:
            item["ozRub"] = round(item["price"] * 31.1034768, 2)
            item["ozUsd"] = round(item["price"] * 31.1034768 / usd, 2)

    return {
        "crypto": {
            "items": (crypto or {}).get("items", []),
            "provider": (crypto or {}).get("provider"),
            "meta": crypto_meta,
        },
        "metals": {"items": (metals or {}).get("items", []), "meta": metals_meta},
        "fx": _fx_block(fx, fx_meta),
        "keyRate": {"value": (key_rate or {}).get("value"), "date": (key_rate or {}).get("date"), "meta": key_meta},
        "serverTime": now_msk(),
    }


def _safe_source(name, ttl, builder):
    try:
        return source(name, ttl, builder)
    except Exception as exc:  # noqa: BLE001 - один источник не должен ронять выдачу
        return None, {"ok": False, "error": str(exc)[:300], "stale": False, "updated": None}


def api_deposits():
    data, meta = _safe_source("dep_direct", DEPOSIT_TTL, build_direct_banks)
    items = data or []
    if not items:
        raise RuntimeError("Сайты банков: вклады недоступны")
    items.sort(key=lambda x: (-(x.get("rate") or 0), x.get("bank") or ""))
    key_rate, key_meta = _safe_source("key_rate", 21600, build_key_rate)
    return {
        "items": items,
        "sources": [{"key": "direct", "name": "Банки", "count": len(items), "meta": meta}],
        "meta": {"ok": meta.get("ok"), "stale": meta.get("stale"), "updated": meta.get("updated")},
        "keyRate": {"value": (key_rate or {}).get("value"), "date": (key_rate or {}).get("date"), "meta": key_meta},
        "serverTime": now_msk(),
    }


# ---------------------------------------------------------------- realty
BN_URL = "https://www.bn.ru/kvartiry-vtorichka/"
BN_PAGES = 20


def _parse_bn(html):
    parts = re.split(r'(?=<a href="/detail/flats/\d+/")', html)
    items = []
    for part in parts:
        m = re.match(r'<a href="(/detail/flats/\d+/)"', part)
        if not m:
            continue
        seg = part[:25000]
        headline = re.search(r'catalog-item__headline">(.*?)</div>', seg, re.S)
        sub = re.search(r'catalog-item__sub-headline">(.*?)</div>', seg, re.S)
        price = re.search(r"catalog-item__price\">([\d\s\u00a0]+)", seg)
        ppm = re.search(r"catalog-item__price-unit\">([\d\s\u00a0]+)", seg)
        address = re.search(r'catalog-item__address">(.*?)</div>', seg, re.S)
        district = re.search(r'catalog-item__district">(.*?)</div>', seg, re.S)
        metro = re.search(r'catalog-item__metro-name">(.*?)</span>', seg, re.S)
        image = re.search(r'data-srcset="(//static\.bn\.ru[^"]+)"', seg) or re.search(r'src="(//static\.bn\.ru[^"]+)"', seg)
        if not headline or not price:
            continue
        title = _clean(headline.group(1))
        subtext = _clean(sub.group(1)) if sub else ""
        if "доля" in subtext.lower() or "комната" in title.lower():
            continue
        addr = _clean(address.group(1)) if address else ""
        district_text = _clean(district.group(1)) if district else ""
        city_m = re.match(r"([^,]+?)\s+(?:г|п|д|рп)\.", addr)
        if "область" in addr.lower() or (city_m and city_m.group(1).strip().lower() in REGION_CITIES):
            continue
        if not any(x in district_text.lower() for x in SPB_DISTRICTS):
            continue
        area = re.search(r"([\d.,]+)\s*м", title)
        rooms = re.search(r"(\d)-комнатная", title)
        img = image.group(1) if image else ""
        if img.startswith("//"):
            img = "https:" + img
        elif img.startswith("/"):
            img = "https://www.bn.ru" + img
        items.append({
            "id": "bn:" + m.group(1).strip("/").rsplit("/", 1)[-1],
            "source": "БН.ру",
            "city": "Санкт-Петербург",
            "title": title,
            "price": int(re.sub(r"\D", "", price.group(1))),
            "priceM2": int(re.sub(r"\D", "", ppm.group(1))) if ppm else None,
            "area": _num(area.group(1)) if area else None,
            "rooms": "Студия" if "студи" in title.lower() else (rooms.group(1) if rooms else ""),
            "address": addr,
            "district": district_text,
            "metro": _clean(metro.group(1)) if metro else "",
            "sub": subtext,
            "img": img,
            "url": "https://www.bn.ru" + m.group(1),
        })
    return items


def build_bn():
    items, seen = [], set()
    for page in range(1, BN_PAGES + 1):
        try:
            html = http_text(BN_URL + ("" if page == 1 else f"?page={page}"), timeout=45)
        except Exception:
            break
        page_items = _parse_bn(html)
        if not page_items:
            break
        for item in page_items:
            if item["id"] not in seen:
                seen.add(item["id"])
                items.append(item)
    if not items:
        raise RuntimeError("bn.ru: не удалось разобрать объявления")
    return items


def build_mirkvartir_stats():
    text = http_text("https://www.mirkvartir.ru/%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0/", timeout=45)
    avg = re.search(r"Средняя рыночная цена квартиры в Москве составляет ([\d\s\u00a0]+) руб\. и ([\d\s\u00a0]+) руб\. за м²", text)
    rng = re.search(r"от ([\d\s\u00a0]+) ₽ до ([\d\s\u00a0]+) ₽", text)
    count = re.search(r"В базе недвижимости ([\d\s\u00a0]+) объявлений", text)
    if not avg:
        raise RuntimeError("mirkvartir.ru: не найдена средняя цена")
    return {
        "city": "Москва",
        "avgPrice": int(re.sub(r"\D", "", avg.group(1))),
        "avgM2": int(re.sub(r"\D", "", avg.group(2))),
        "min": int(re.sub(r"\D", "", rng.group(1))) if rng else None,
        "max": int(re.sub(r"\D", "", rng.group(2))) if rng else None,
        "count": int(re.sub(r"\D", "", count.group(1))) if count else None,
        "source": "Мир квартир",
        "url": "https://www.mirkvartir.ru/%D0%9C%D0%BE%D1%81%D0%BA%D0%B2%D0%B0/",
    }


AVITO_URL = "https://www.avito.ru/rossiya/kvartiry/prodam"
AVITO_PAGES = 3
AVITO_JS = r"""JSON.stringify([...document.querySelectorAll('[data-marker="item"]')].map((card) => ({
  id: card.dataset.itemId,
  title: card.querySelector('[itemprop="name"]')?.innerText,
  url: card.querySelector('a[itemprop="url"]')?.href,
  price: card.querySelector('[itemprop="price"]')?.content,
  img: card.querySelector('img')?.src,
  addr: card.querySelector('[data-marker="item-address"]')?.innerText,
  text: card.innerText
})))"""

CIAN_URL = "https://spb.cian.ru/cat.php?deal_type=sale&engine_version=2&offer_type=flat&region=2"
CIAN_PAGES = 20
CIAN_JS = r"""JSON.stringify([...document.querySelectorAll('article[data-name="CardComponent"]')].map((card) => ({
  url: card.querySelector('a[href*="/sale/flat/"]')?.href,
  title: card.querySelector('[data-mark="OfferTitle"]')?.innerText,
  price: card.querySelector('[data-mark="MainPrice"]')?.innerText,
  subtitle: card.querySelector('[data-mark="OfferSubtitle"]')?.innerText,
  img: card.querySelector('img')?.src,
  text: card.innerText
})))"""

CITY_SLUGS = {
    "sankt-peterburg": "Санкт-Петербург",
    "moskva": "Москва",
    "novosibirsk": "Новосибирск",
    "ekaterinburg": "Екатеринбург",
    "kazan": "Казань",
    "krasnodar": "Краснодар",
    "nizhniy_novgorod": "Нижний Новгород",
    "chelyabinsk": "Челябинск",
    "samara": "Самара",
    "ufa": "Уфа",
    "rostov-na-donu": "Ростов-на-Дону",
    "krasnoyarsk": "Красноярск",
    "perm": "Пермь",
    "voronezh": "Воронеж",
    "volgograd": "Волгоград",
    "groznyy": "Грозный",
    "abakan": "Абакан",
    "yaroslavl": "Ярославль",
    "ryazan": "Рязань",
    "krasnogorsk": "Красногорск",
    "kirov": "Киров",
    "vologda": "Вологда",
    "yoshkar-ola": "Йошкар-Ола",
    "novaya_usman": "Новая Усмань",
    "orenburg": "Оренбург",
    "tver": "Тверь",
    "kaliningrad": "Калининград",
    "tyumen": "Тюмень",
    "sochi": "Сочи",
    "domodedovo": "Домодедово",
    "voskresenskoe": "Воскресенское",
    "odintsovo": "Одинцово",
}


def _clean_city(value):
    city = _clean(value)
    city = re.sub(r"^г\.о\.\s*", "", city, flags=re.I)
    city = re.sub(r"^г\.\s*", "", city, flags=re.I)
    city = re.sub(r"\s*[·•]\s*$", "", city)
    return city.strip()


def _avito_city(parts, addr, url):
    text = " ".join(parts)
    if "Санкт-Петербург" in text:
        return "Санкт-Петербург"
    if re.search(r"\bМосква\b", text):
        return "Москва"
    region_city = re.search(r"(?:област\w*|обл\.|край|Республика|респ\.|АО|автономный округ)[^,]*,\s*([^,]+)", addr)
    if region_city:
        city = _clean_city(region_city.group(1))
        if city and not re.search(r"(ул\.|просп|переул|наб\.|шоссе|бульвар|пл\.|линия|д\.|р-н)", city, re.I):
            return city
    city_prefix = re.search(r"\bг\.(?:о\.)?\s*([^,]+)", addr)
    if city_prefix:
        return _clean_city(city_prefix.group(1))
    if "," in addr:
        first, last = addr.split(",", 1)[0], addr.split(",")[-1].strip()
        if not re.search(r"(ул\.|просп|пр-т|переул|наб\.|шоссе|бульвар|пл\.|линия|д\.)", first, re.I):
            if not re.search(r"\d", last) and not re.search(r"(ул\.|просп|пр-т|переул|наб\.|шоссе|бульвар|пл\.|линия|д\.)", last, re.I):
                return _clean_city(last)
    slug = re.search(r"avito\.ru/([^/]+)/", url)
    if slug:
        value = slug.group(1)
        if value in CITY_SLUGS:
            return CITY_SLUGS[value]
        for prefix in ("moskovskaya_oblast_", "leningradskaya_oblast_"):
            if value.startswith(prefix) and value[len(prefix):] in CITY_SLUGS:
                return CITY_SLUGS[value[len(prefix):]]
    return ""


def build_avito():
    rows = browser_json_pages(AVITO_URL, AVITO_JS, AVITO_PAGES, first_wait=14, wait=6)
    if not rows:
        rows = browser_json_pages(AVITO_URL, AVITO_JS, 1, first_wait=18)
    items, seen = [], set()
    for row in rows:
        title = _clean(row.get("title"))
        url = (row.get("url") or "").split("?")[0]
        price = _digits(row.get("price"))
        if not title or not url or not (1_000_000 <= price <= 1_000_000_000):
            continue
        raw_addr = row.get("addr") or ""
        text = row.get("text") or ""
        parts = []
        for raw in raw_addr.splitlines():
            part = _clean(raw)
            part = re.sub(r"\s*·\s*[\d,.]+\s*·\s*\d+\s*отзыв\w*", "", part)
            part = re.sub(r"^\s*[\d,.]+\s*·\s*\d+\s*отзыв\w*", "", part).strip()
            part = re.sub(r"\s*[·•]\s*$", "", part).strip()
            if not part or "отзыв" in part.lower():
                continue
            if part.startswith(("ЖК", "Экопоселок", "Квартал", "Микрорайон")):
                continue
            parts.append(part)
        addr, district, metro = "", "", ""
        for part in parts:
            if "мин." in part:
                if not metro:
                    metro = part.split(",")[0].strip()
                continue
            if re.match(r"р-н\s+", part):
                if not district:
                    district = re.sub(r"^р-н\s+", "", part).strip()
                continue
            if not addr and (part.startswith(("Санкт-Петербург", "Москва")) or "," in part):
                addr = part
        if not addr:
            addr = next((p for p in parts if re.search(r"(ул\.|просп|пр-т|переул|наб\.|шоссе|бульвар|пл\.|линия)", p)), "")
        city = _avito_city(parts, addr, url)
        if not addr and city:
            addr = city
        area = re.search(r"([\d.,]+)\s*м²", title)
        room_match = re.search(r"(\d+)-к", title)
        rooms = "Студия" if "студи" in title.lower() else (room_match.group(1) if room_match else "")
        ppm = re.search(r"([\d][\d\u00a0 ]*)\s*₽\s*за\s*м²", text)
        item_id = str(row.get("id") or url.rsplit("_", 1)[-1].split("?")[0])
        if item_id in seen:
            continue
        seen.add(item_id)
        items.append({
            "id": "avito:" + item_id,
            "source": "Авито",
            "city": city,
            "title": title,
            "price": price,
            "priceM2": _digits(ppm.group(1)) if ppm else None,
            "area": _num(area.group(1)) if area else None,
            "rooms": rooms,
            "address": addr,
            "district": district,
            "metro": metro,
            "sub": "",
            "img": row.get("img") or "",
            "url": url,
        })
    if not items:
        raise RuntimeError("Авито: не удалось получить объявления (антибот)")
    return items


def build_cian():
    rows = browser_json_pages(CIAN_URL, CIAN_JS, CIAN_PAGES, first_wait=10, wait=5)
    items, seen = [], set()
    for row in rows:
        title = _clean(row.get("title"))
        subtitle = _clean(row.get("subtitle"))
        url = (row.get("url") or "").split("?")[0]
        text = row.get("text") or ""
        layout = subtitle if re.search(r"(комн|студи|м²)", subtitle, re.I) else title
        if not layout or not url or "своб. планировка" in (layout + " " + title).lower():
            continue
        area_match = re.search(r"([\d.,]+)\s*м²", layout) or re.search(r"([\d.,]+)\s*м²", title)
        area = _num(area_match.group(1)) if area_match else None
        if area and not (10 <= area <= 300):
            continue
        price = _digits(row.get("price"))
        if not (1_000_000 <= price <= 500_000_000):
            continue
        lines = [_clean(x) for x in text.splitlines() if _clean(x)]
        addr = next((line for line in lines if line.startswith("Санкт-Петербург")), "")
        if not addr:
            continue
        sale = re.search(r"/sale/flat/(\d+)/", url)
        if not sale or sale.group(1) in seen:
            continue
        seen.add(sale.group(1))
        district_m = re.search(r"р-н\s+([^,]+)", addr)
        metro_m = re.search(r"м\.\s*([^,]+)", addr)
        ppm = re.search(r"([\d][\d\u00a0 ]*)\s*₽/м²", text)
        room_match = re.search(r"(\d+)-комн", layout) or re.search(r"(\d+)-комн", title)
        rooms = "Студия" if "студия" in layout.lower() else (room_match.group(1) if room_match else "")
        items.append({
            "id": "cian:" + sale.group(1),
            "source": "Циан",
            "city": _clean_city(addr.split(",")[0]) or "Санкт-Петербург",
            "title": layout,
            "price": price,
            "priceM2": _digits(ppm.group(1)) if ppm else (round(price / area) if area else None),
            "area": area,
            "rooms": rooms,
            "address": addr,
            "district": _clean(district_m.group(1)) if district_m else "",
            "metro": _clean(metro_m.group(1)) if metro_m else "",
            "sub": title if title != layout else "",
            "img": row.get("img") or "",
            "url": url,
        })
    if not items:
        raise RuntimeError("Циан: не удалось получить объявления (антибот)")
    return items


# Яндекс.Недвижимость отдаёт готовое состояние страницы обычному HTTP-клиенту:
# один запрос — 23 карточки, без Chrome и антибота. Национальная выдача
# ограничена 25 страницами, поэтому объём добираем крупными городами.
YANDEX_RUSSIA_URL = "https://realty.yandex.ru/rossiya/kupit/kvartira/?rgid=143"
YANDEX_PAGES = 25
YANDEX_CITY_PAGES = 10
YANDEX_CITIES = (
    ("moskva", "Москва"),
    ("sankt-peterburg", "Санкт-Петербург"),
    ("novosibirsk", "Новосибирск"),
    ("ekaterinburg", "Екатеринбург"),
    ("kazan", "Казань"),
    ("krasnodar", "Краснодар"),
    ("chelyabinsk", "Челябинск"),
    ("samara", "Самара"),
    ("ufa", "Уфа"),
    ("rostov-na-donu", "Ростов-на-Дону"),
    ("krasnoyarsk", "Красноярск"),
    ("perm", "Пермь"),
    ("voronezh", "Воронеж"),
    ("volgograd", "Волгоград"),
    ("tyumen", "Тюмень"),
    ("sochi", "Сочи"),
    ("kaliningrad", "Калининград"),
    ("orenburg", "Оренбург"),
    ("izhevsk", "Ижевск"),
    ("irkutsk", "Иркутск"),
    ("vladivostok", "Владивосток"),
    ("mahachkala", "Махачкала"),
    ("tomsk", "Томск"),
    ("omsk", "Омск"),
    ("stavropol", "Ставрополь"),
    ("barnaul", "Барнаул"),
    ("kemerovo", "Кемерово"),
    ("novokuznetsk", "Новокузнецк"),
    ("ryazan", "Рязань"),
    ("astrahan", "Астрахань"),
    ("penza", "Пенза"),
    ("lipetsk", "Липецк"),
    ("tula", "Тула"),
    ("kirov", "Киров"),
    ("cheboksary", "Чебоксары"),
)


def _yandex_url(slug: str, page: int) -> str:
    base = f"https://realty.yandex.ru/{slug}/kupit/kvartira/" if slug else YANDEX_RUSSIA_URL
    if page <= 1:
        return base
    return base + ("&" if "?" in base else "?") + f"page={page}"


def _parse_yandex(html: str, fallback_city: str = ""):
    marker = "window.INITIAL_STATE = "
    start = html.find(marker)
    if start < 0:
        raise RuntimeError("Яндекс: нет состояния страницы")
    start += len(marker)
    end = html.find("</script>", start)
    if end < 0:
        raise RuntimeError("Яндекс: не найден конец состояния")
    state = json.loads(html[start:end].rstrip(" ;\n"))
    entities = ((state.get("search") or {}).get("offers") or {}).get("entities") or []
    items = []
    for entity in entities:
        if entity.get("offerCategory") != "APARTMENT" or entity.get("offerType") != "SELL":
            continue
        price = (entity.get("price") or {}).get("value")
        area = (entity.get("area") or {}).get("value")
        if not price or not (300_000 <= price <= 1_000_000_000):
            continue
        if area and not (10 <= area <= 300):
            continue
        location = entity.get("location") or {}
        components = (location.get("structuredAddress") or {}).get("component") or []
        city = next((c.get("value") for c in components if c.get("regionType") == "CITY"), "") or fallback_city
        if not city:
            continue
        address = location.get("address") or location.get("geocoderAddress") or ""
        if address and city not in address:
            address = f"{city}, {address}"
        rooms = entity.get("roomsTotal")
        rooms_text = "Студия" if rooms in (0, "0", "STUDIO") else (str(rooms) if rooms else "")
        area_text = f"{area:g}" if isinstance(area, (int, float)) else ""
        title = (f"{rooms_text}-комн. квартира" if rooms_text else "Квартира") + (f", {area_text} м²" if area_text else "")
        images = entity.get("minicardImages") or entity.get("mainImages") or entity.get("origImages") or []
        img = images[0] if images else ""
        if img.startswith("//"):
            img = "https:" + img
        flat = entity.get("flatType") or ""
        items.append({
            "id": "yandex:" + str(entity.get("offerId")),
            "source": "Яндекс",
            "city": _clean_city(city),
            "title": title,
            "price": int(price),
            "priceM2": round(price / area) if area else None,
            "area": area,
            "rooms": rooms_text,
            "address": _clean(address),
            "district": "",
            "metro": _clean((location.get("metro") or {}).get("name") or ""),
            "sub": "Новостройка" if flat.startswith("NEW") else "Вторичка",
            "img": img,
            "url": f"https://realty.yandex.ru/offer/{entity.get('offerId')}/",
        })
    return items


def build_yandex():
    tasks = [(None, page, "") for page in range(1, YANDEX_PAGES + 1)]
    tasks += [(slug, page, name) for slug, name in YANDEX_CITIES for page in range(1, YANDEX_CITY_PAGES + 1)]

    def fetch(task):
        slug, page, fallback = task
        url = _yandex_url(slug or "", page)
        last = None
        for _ in range(2):
            try:
                return _parse_yandex(http_text(url, timeout=45), fallback)
            except Exception as exc:  # noqa: BLE001 - одна страница не должна ронять всю выборку
                last = exc
                time.sleep(1)
        raise last

    items, seen = [], set()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch, task) for task in tasks]
        for future in as_completed(futures):
            try:
                rows = future.result()
            except Exception:
                continue
            for item in rows:
                if item["id"] not in seen:
                    seen.add(item["id"])
                    items.append(item)
    if not items:
        raise RuntimeError("Яндекс: не удалось получить объявления")
    return items


def api_realty():
    jobs = [
        ("realty_bn", 10800, build_bn),
        ("realty_avito", 10800, build_avito),
        ("realty_cian", 10800, build_cian),
        ("realty_yandex", 10800, build_yandex),
        ("realty_moscow", 21600, build_mirkvartir_stats),
    ]
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda job: _safe_source(*job), jobs))

    listings = []
    metas = {}
    for (key, _, _), (data, meta) in zip(jobs, results):
        metas[key] = (data, meta)
        if key != "realty_moscow" and data:
            listings.extend(data)
    moscow = metas["realty_moscow"][0]

    if not listings and not moscow:
        raise RuntimeError("Недвижимость: источники недоступны")

    avito_items = metas["realty_avito"][0] or []
    yandex_items = metas["realty_yandex"][0] or []
    for item in yandex_items:
        item["source"] = "Яндекс"
    sample = avito_items + yandex_items or listings
    russia = None
    if sample:
        # shortcut: медиана и средняя цена м² по выборке карточек, не по всему рынку; перейти на API Яндекса при необходимости.
        prices = sorted(x["price"] for x in sample if x.get("price"))
        ppsm = [x["priceM2"] for x in sample if x.get("priceM2")]
        cities = {x.get("city") for x in sample if x.get("city")}
        russia = {
            "city": "Россия",
            "count": len(sample),
            "cities": len(cities),
            "median": prices[len(prices) // 2] if prices else None,
            "avgM2": round(sum(ppsm) / len(ppsm)) if ppsm else None,
            "source": "Авито и Яндекс, вся Россия" if avito_items and yandex_items else "Яндекс, вся Россия" if yandex_items else "Авито, вся Россия",
            "url": YANDEX_RUSSIA_URL if yandex_items else AVITO_URL,
            "sample": True,
        }

    sources = []
    scopes = {"realty_bn": "СПб", "realty_avito": "Россия", "realty_cian": "СПб",
              "realty_yandex": "Россия", "realty_moscow": "Москва"}
    for key, label, _ in (("realty_bn", "БН.ру", build_bn), ("realty_avito", "Авито", build_avito),
                          ("realty_cian", "Циан", build_cian), ("realty_yandex", "Яндекс", build_yandex),
                          ("realty_moscow", "Мир квартир", build_mirkvartir_stats)):
        data, meta = metas[key]
        count = len(data) if isinstance(data, list) else (1 if data else 0)
        sources.append({"key": key.replace("realty_", ""), "name": label, "scope": scopes[key],
                        "count": count, "meta": meta})

    meta_list = [m for _, m in metas.values()]
    return {
        "items": listings,
        "stats": {"moscow": moscow, "russia": russia},
        "sources": sources,
        "meta": {
            "ok": any(m.get("ok") for m in meta_list),
            "stale": any(m.get("stale") for m in meta_list),
            "updated": max((m.get("updated") or "" for m in meta_list), default=None),
        },
        "serverTime": now_msk(),
    }


def _yandex_offer_images(offer_id):
    html = http_text(f"https://realty.yandex.ru/offer/{offer_id}/", timeout=35)
    marker = "window.INITIAL_STATE = "
    start = html.find(marker)
    if start < 0:
        return []
    start += len(marker)
    end = html.find("</script>", start)
    if end < 0:
        return []
    state = json.loads(html[start:end].rstrip(" ;\n"))
    card = (state.get("offerCard") or {}).get("card") or {}
    raw = card.get("mainImages") or card.get("minicardImages") or card.get("origImages") or []
    images = []
    for value in raw:
        if not value:
            continue
        image = value if value.startswith("http") else ("https:" + value if value.startswith("//") else value)
        if image not in images:
            images.append(image)
    return images[:12]


def api_realty_photos(params):
    item_id = str((params or {}).get("id") or "").strip()
    if not item_id.startswith("yandex:"):
        return {"id": item_id, "images": []}
    hit = PHOTOS_MEM.get(item_id)
    if hit and hit["exp"] > time.time():
        return hit["value"]
    try:
        images = _yandex_offer_images(item_id.split(":", 1)[1])
    except Exception:
        images = []
    value = {"id": item_id, "images": images}
    if images:
        with LOCK:
            PHOTOS_MEM[item_id] = {"exp": time.time() + 21600, "value": value}
    return value


# ---------------------------------------------------------------- ai (YandexGPT)
YANDEX_GPT_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
YANDEX_GPT_SYSTEM = (
    "Ты — AI-аналитик сервиса «Монетка». Отвечай по-русски, кратко и по делу, "
    "опирайся только на переданные данные. Ты умеешь разбирать портфель (доли, риски, "
    "концентрация, доходность), сравнивать вклады по ставке, сумме и сроку, объяснять "
    "курсы валют и цены металлов, смотреть статистику недвижимости и считать простые "
    "сценарии по данным. Если в вопросе есть сумма, срок или доля, обязательно посчитай "
    "результат и сравни варианты по числам, а не только перечисляй. Если спрашивают "
    "о доходности портфеля, различай общую прибыль в процентах (pnlPct) и годовую "
    "доходность XIRR (irrPct); называй обе, если они есть. Учитывай ограничения "
    "min/max, срок и валюту: если параметры не подходят, не предлагай вариант; если срок "
    "другой, пересчитай доход пропорционально или предупреди. Называй конкретные "
    "активы и числа. Если данных не хватает, скажи, чего не хватает, и задай один "
    "уточняющий вопрос. Не выдумывай цены, активы "
    "и доходность. Не давай персональных инвестиционных рекомендаций: формулируй "
    "наблюдения и варианты. На вопрос «что делать» предложи 1–2 нейтральных варианта "
    "и оговорку, что решение принимает пользователь. В конце добавь отдельной строкой: "
    "«Это не инвестиционная рекомендация.»"
)

YANDEX_COMMENTARY_SYSTEM = (
    "Ты — AI-аналитик сервиса «Монетка». Тебе дают факты и уже рассчитанный "
    "статистический прогноз. Не меняй числа и не придумывай новые. Объясни "
    "2–4 предложениями: режим рынка, что подтверждает сценарий, главные риски "
    "и на что смотреть. Учитывай переданные факторы. Уверенность модели — "
    "это условная оценка, не вероятность; не называй её вероятностью. Пиши "
    "по-русски, кратко, без персональных инвестиционных рекомендаций."
)


def _yandex_completion(messages, *, temperature=0.3, max_tokens=700, timeout=45):
    key = (os.environ.get("YANDEX_GPT_API_KEY") or "").strip()
    folder = (os.environ.get("YANDEX_GPT_FOLDER_ID") or "").strip()
    if not key or not folder:
        raise RuntimeError("Нейросеть не настроена: администратору нужно добавить ключ API")
    model = (os.environ.get("YANDEX_GPT_MODEL") or "yandexgpt/latest").strip()
    model_uri = model if model.startswith("gpt://") else f"gpt://{folder}/{model}"
    body = json.dumps({
        "modelUri": model_uri,
        "completionOptions": {"stream": False, "temperature": temperature, "maxTokens": max_tokens},
        "messages": messages,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(YANDEX_GPT_URL, data=body, method="POST", headers={
        "Authorization": f"Api-Key {key}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code in (401, 403):
            raise RuntimeError(
                "Нейросеть отклонила ключ: администратору нужно проверить ключ API, "
                "права сервисного аккаунта и scope yc.ai.languageModels.execute"
            ) from exc
        raise RuntimeError(f"Нейросеть: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Нейросеть недоступна: {exc.reason}") from exc
    result = data.get("result") or {}
    alternatives = result.get("alternatives") or []
    answer = ((alternatives[0].get("message") or {}).get("text") or "").strip() if alternatives else ""
    if not answer:
        raise RuntimeError("Нейросеть вернула пустой ответ")
    return {"answer": answer, "model": model, "usage": result.get("usage")}


def api_ai(payload):
    if not isinstance(payload, dict):
        raise ValueError("Некорректный запрос")
    question = str(payload.get("question") or "").strip()[:1200]
    if not question:
        raise ValueError("Введите вопрос")
    context = str(payload.get("context") or "").strip()[:8000]
    messages = [{"role": "system", "text": YANDEX_GPT_SYSTEM}]
    history = payload.get("history") or []
    if isinstance(history, list):
        for item in history[-6:]:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            text = str(item.get("text") or "").strip()[:1500]
            if role in ("user", "assistant") and text:
                messages.append({"role": role, "text": text})
    messages.append({"role": "user", "text": f"Данные:\n{context or 'Нет данных'}\n\nВопрос: {question}"})
    return _yandex_completion(messages, temperature=0.3, max_tokens=700, timeout=45)


def _num_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _std(values):
    if len(values) < 2:
        return 0.0
    avg = _mean(values)
    return (sum((value - avg) ** 2 for value in values) / len(values)) ** 0.5


def _log_returns(prices):
    return [
        math.log(prices[i] / prices[i - 1])
        for i in range(1, len(prices))
        if prices[i] > 0 and prices[i - 1] > 0
    ]


def _model_path(history, horizon, steps_per_day, model):
    last = history[-1]
    returns = _log_returns(history)
    window = min(len(returns), 20)
    drift = _mean(returns[-window:]) if window else 0.0
    ma_window = min(len(history), 20)
    ma = _mean(history[-ma_window:])
    path = []
    for day in range(1, horizon + 1):
        step = day * steps_per_day
        if model == "random":
            value = last
        elif model == "momentum":
            value = last * math.exp(drift * step * 0.7)
        else:
            value = last + (ma - last) * (1 - math.exp(-step / 5)) * 0.5
        path.append(value)
    return path


def _backtest(history, horizon, steps_per_day):
    backtest_days = 2 if steps_per_day > 1 else max(1, horizon)
    step_points = backtest_days * steps_per_day
    start = max(1, len(history) - 180)
    end = len(history) - step_points
    models = ("random", "momentum", "reversion")
    errors = {model: [] for model in models}
    preds = {model: [] for model in models}
    actuals = []
    for i in range(start, end):
        current = history[i]
        actual = history[i + step_points]
        actuals.append((current, actual))
        for model in models:
            pred = _model_path(history[:i + 1], backtest_days, steps_per_day, model)[-1]
            preds[model].append(pred)
            errors[model].append(abs(pred / actual - 1))
    samples = len(actuals)
    if not samples:
        return {
            "samples": 0,
            "directionAccuracyPct": 50.0,
            "mapePct": 0.0,
            "horizonDays": backtest_days,
            "weights": {model: round(1 / len(models), 3) for model in models},
        }
    mape = {model: _mean(errors[model]) * 100 for model in models}
    weights = {model: 1 / (mape[model] + 1e-6) for model in models}
    total = sum(weights.values()) or 1
    weights = {model: value / total for model, value in weights.items()}
    ensemble = [
        sum(weights[model] * preds[model][index] for model in models)
        for index in range(samples)
    ]
    ensemble_mape = _mean([
        abs(pred / actual - 1)
        for pred, (_, actual) in zip(ensemble, actuals)
    ]) * 100
    hits = [
        1 if (pred >= current) == (actual >= current) else 0
        for pred, (current, actual) in zip(ensemble, actuals)
    ]
    return {
        "samples": samples,
        "directionAccuracyPct": round(_mean(hits) * 100, 1),
        "mapePct": round(ensemble_mape, 2),
        "horizonDays": backtest_days,
        "weights": {model: round(value, 3) for model, value in weights.items()},
    }


def _stat_forecast(history, horizon, price, steps_per_day):
    models = ("random", "momentum", "reversion")
    backtest = _backtest(history, horizon, steps_per_day)
    weights = backtest["weights"]
    paths = {model: _model_path(history, horizon, steps_per_day, model) for model in models}
    points = [
        sum(weights[model] * paths[model][day] for model in models)
        for day in range(horizon)
    ]
    floor, ceil = price * 0.5, price * 1.5
    points = [round(min(max(value, floor), ceil), 4) for value in points]
    change = (points[-1] / price - 1) * 100 if price else 0
    direction = "up" if change > 0.5 else "down" if change < -0.5 else "flat"
    returns = _log_returns(history)
    window = min(len(returns), 20)
    vol = _std(returns[-window:]) if window else 0.0
    sigma_h = vol * math.sqrt(max(1, horizon * steps_per_day))
    band = min(max((math.exp(1.28 * sigma_h) - 1) * 100, 1.0), 25.0)
    volatility = min(max((math.exp(sigma_h) - 1) * 100, 0.0), 50.0)
    accuracy = backtest["directionAccuracyPct"] / 100
    samples = backtest["samples"]
    confidence = 0.3 + (accuracy - 0.5) * 0.9 + (min(samples, 30) / 30) * 0.1 if samples else 0.35
    confidence = min(max(confidence, 0.2), 0.8)
    recent = history[-20:] or [price]
    label = {"up": "рост", "down": "снижение", "flat": "боковик"}[direction]
    summary = (
        f"Статистический сценарий: {label} на {horizon} дн. Ожидаемое изменение "
        f"{change:+.1f}%. Волатильность {volatility:.1f}%. Бэктест на "
        f"{backtest['horizonDays']} дн.: направление {backtest['directionAccuracyPct']:.0f}% "
        f"(n={samples}), средняя ошибка {backtest['mapePct']:.1f}%."
    )
    return {
        "direction": direction,
        "changePct": round(change, 2),
        "confidence": round(confidence, 2),
        "bandPct": round(band, 2),
        "volatilityPct": round(volatility, 2),
        "summary": summary,
        "points": points,
        "support": round(min(recent), 4),
        "resistance": round(max(recent), 4),
        "backtest": backtest,
        "model": "ensemble",
    }


def _forecast_factors(market, kind, item):
    fx_items = (market.get("fx") or {}).get("items") or []
    usd = next((_num_or_none(x.get("value")) for x in fx_items if x.get("code") == "USD"), None)
    factors = {
        "keyRate": (market.get("keyRate") or {}).get("value"),
        "usdRub": usd,
        "change24hPct": round(_num_or_none(item.get("change24h")) or 0, 2),
    }
    if kind == "crypto":
        cryptos = (market.get("crypto") or {}).get("items") or []
        breadth = [_num_or_none(x.get("change24h")) for x in cryptos]
        breadth = [value for value in breadth if value is not None]
        btc = next((x for x in cryptos if x.get("id") == "bitcoin"), None)
        btc_change = _num_or_none(btc.get("change24h")) if btc else None
        factors["marketBreadthPct"] = round(_mean(breadth), 2) if breadth else None
        factors["btcChange24hPct"] = round(btc_change, 2) if btc_change is not None else None
        factors["volumeUsd"] = _num_or_none(item.get("volume"))
    elif kind == "metal":
        metals = (market.get("metals") or {}).get("items") or []
        gold = next((_num_or_none(x.get("price")) for x in metals if x.get("code") == "XAU"), None)
        silver = next((_num_or_none(x.get("price")) for x in metals if x.get("code") == "XAG"), None)
        factors["goldSilverRatio"] = round(gold / silver, 2) if gold and silver else None
    else:
        cross = [
            _num_or_none(x.get("change24h"))
            for x in fx_items
            if x.get("code") in ("USD", "EUR", "CNY", "GBP") and x.get("code") != item.get("code")
        ]
        cross = [value for value in cross if value is not None]
        factors["fxCrossChangePct"] = round(_mean(cross), 2) if cross else None
    return factors


def _factor_text(factors):
    labels = {
        "keyRate": ("ключевая ставка", "%"),
        "usdRub": ("USD/RUB", ""),
        "change24hPct": ("изменение за 24ч", "%"),
        "marketBreadthPct": ("средняя динамика крипторынка", "%"),
        "btcChange24hPct": ("BTC за 24ч", "%"),
        "volumeUsd": ("объём 24ч", "usd"),
        "goldSilverRatio": ("золото/серебро", ""),
        "fxCrossChangePct": ("другие основные валюты", "%"),
    }
    parts = []
    for key, (label, suffix) in labels.items():
        value = factors.get(key)
        if value is None:
            continue
        if suffix == "usd":
            parts.append(f"{label}: ${value / 1e6:.0f}M")
        elif key == "keyRate":
            parts.append(f"{label}: {value:g}%")
        elif suffix == "%":
            parts.append(f"{label}: {value:+.2f}%")
        elif key == "usdRub":
            parts.append(f"{label}: {value:.2f}")
        else:
            parts.append(f"{label}: {value:.1f}")
    return "; ".join(parts) or "нет дополнительных факторов"


def api_forecast(payload):
    if not isinstance(payload, dict):
        raise ValueError("Некорректный запрос")
    kind = str(payload.get("kind") or "").strip()
    asset_id = str(payload.get("id") or "").strip()
    if kind not in ("crypto", "metal", "fx"):
        raise ValueError("Прогноз доступен для криптовалют, драгметаллов и валют")
    if not asset_id:
        raise ValueError("Не выбран актив")
    market = api_market()
    if kind == "crypto":
        item = next((x for x in market["crypto"]["items"] if str(x.get("id")) == asset_id), None)
        unit = "USD"
        name = item.get("name") if item else None
        symbol = item.get("symbol") if item else None
        default_horizon = 30
    elif kind == "metal":
        item = next((x for x in market["metals"]["items"]
                     if str(x.get("id")) == asset_id or str(x.get("code")) == asset_id), None)
        unit = "RUB/g"
        name = item.get("name") if item else None
        symbol = item.get("code") if item else None
        default_horizon = 30
    else:
        item = next((x for x in market["fx"]["items"] if str(x.get("code")) == asset_id), None)
        unit = "RUB"
        name = item.get("name") if item else None
        symbol = item.get("code") if item else None
        default_horizon = 30
    if not item:
        raise ValueError("Актив не найден")
    try:
        horizon = int(payload.get("horizon") or default_horizon)
    except (TypeError, ValueError):
        horizon = default_horizon
    horizon = max(5, min(180, horizon))
    steps_per_day = 1
    history = []
    try:
        if kind == "crypto" and horizon <= 7 and item.get("spark"):
            for value in item.get("spark") or []:
                number = _num_or_none(value)
                if number and number > 0:
                    history.append(number)
            steps_per_day = 8
        else:
            points, _ = _history_points(kind, asset_id, "1y")
            history = [point["c"] for point in points]
    except Exception:
        history = []
    if len(history) < 5:
        fallback = []
        if kind == "fx":
            fallback = _fx_history(asset_id)
        else:
            for value in item.get("spark") or []:
                number = _num_or_none(value)
                if number and number > 0:
                    fallback.append(number)
            if kind == "crypto":
                steps_per_day = 8
        history = fallback
    if len(history) < 5:
        raise ValueError("Недостаточно истории для прогноза" if kind != "fx" else "Не удалось загрузить историю валюты")
    history = [round(value, 4 if kind in ("crypto", "fx") else 2) for value in history]
    price = _num_or_none(item.get("price")) or _num_or_none(item.get("value")) or history[-1]
    forecast = _stat_forecast(history, horizon, price, steps_per_day)
    factors = _forecast_factors(market, kind, item)
    commentary = None
    ai_error = None
    ai_model = None
    usage = None
    direction_label = {"up": "рост", "down": "снижение", "flat": "боковик"}[forecast["direction"]]
    bt = forecast["backtest"]
    factors_text = _factor_text(factors)
    facts_text = (
        f"Актив: {name or asset_id} ({symbol or asset_id}), цена {price:.6g} {unit}, "
        f"горизонт {horizon} дн.\n"
        f"Статистический прогноз: {direction_label}, изменение "
        f"{forecast['changePct']:+.1f}%, диапазон ±{forecast['bandPct']:.1f}%, "
        f"волатильность {forecast['volatilityPct']:.1f}%.\n"
        f"Бэктест на {bt['horizonDays']} дн.: направление "
        f"{bt['directionAccuracyPct']:.0f}% (n={bt['samples']}), средняя ошибка "
        f"{bt['mapePct']:.1f}%.\n"
        f"Уверенность модели: {forecast['confidence'] * 100:.0f}% "
        "(условная оценка, не вероятность).\n"
        f"Поддержка: {forecast['support']:.6g}, сопротивление: {forecast['resistance']:.6g}.\n"
        f"Факторы: {factors_text}.\n"
        f"Последние значения: {', '.join(f'{value:.6g}' for value in history[-12:])}."
    )
    try:
        result = _yandex_completion([
            {"role": "system", "text": YANDEX_COMMENTARY_SYSTEM},
            {"role": "user", "text": f"Факты:\n{facts_text}\n\nДай комментарий к прогнозу."},
        ], temperature=0.2, max_tokens=400, timeout=25)
        commentary = result["answer"].strip()[:800] or None
        ai_model = result.get("model")
        usage = result.get("usage")
    except Exception as exc:  # noqa: BLE001 - прогноз должен вернуться даже без комментария AI
        ai_error = str(exc)[:240]
    forecast.update({
        "asset": {
            "kind": kind,
            "id": asset_id,
            "name": name or asset_id,
            "symbol": symbol or asset_id,
            "unit": unit,
            "price": price,
            "change24h": _num_or_none(item.get("change24h")) or 0,
        },
        "history": history,
        "horizonDays": horizon,
        "commentary": commentary,
        "aiModel": ai_model,
        "aiError": ai_error,
        "usage": usage,
        "factors": factors,
        "factorsText": factors_text,
        "generatedAt": now_msk(),
        "disclaimer": "Числовой прогноз — статистический ансамбль по истории; AI-комментарий — интерпретация факторов. Бэктест не гарантирует будущую точность. Не инвестиционная рекомендация.",
    })
    return forecast


# ---------------------------------------------------------------- http server
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB, **kwargs)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        try:
            if path == "/api/market":
                query = parse_qs(self.path.partition("?")[2])
                fx_only = str((query.get("fx") or ["0"])[0]).lower() in ("1", "true", "yes")
                self.send_json(api_market(force=True, fx_only=fx_only))
                return
            if path == "/api/deposits":
                self.send_json(api_deposits())
                return
            if path == "/api/realty":
                self.send_json(api_realty())
                return
            if path == "/api/history":
                query = parse_qs(self.path.partition("?")[2])
                self.send_json(api_history({key: values[0] for key, values in query.items()}))
                return
            if path == "/api/realty-photos":
                query = parse_qs(self.path.partition("?")[2])
                self.send_json(api_realty_photos({key: values[0] for key, values in query.items()}))
                return
            if path == "/api/health":
                self.send_json({"ok": True, "time": now_msk()})
                return
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=502)
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path not in ("/api/ai", "/api/forecast"):
            self.send_json({"error": "unknown route"}, status=404)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length > 32_000:
                raise ValueError("Слишком большой запрос")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            self.send_json(api_ai(payload) if path == "/api/ai" else api_forecast(payload))
        except ValueError as exc:
            self.send_json({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001
            self.send_json({"error": str(exc)}, status=502)

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, fmt, *args):  # тихий лог
        if args and str(args[1]).startswith(("4", "5")):
            print("[http]", fmt % args)


def main():
    port = int(os.environ.get("PORT", "8787"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Monetka is running: {url}")
    print("Ctrl+C to stop")
    if os.environ.get("NO_BROWSER") != "1":
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBye")


if __name__ == "__main__":
    main()
