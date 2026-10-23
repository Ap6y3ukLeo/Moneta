#!/usr/bin/env python3
"""Монетка — локальный сервер: живые котировки (ЦБ РФ, Bybit), вклады и недвижимость.

Запуск:  python server.py   ->  http://127.0.0.1:8787
Только стандартная библиотека Python 3.10+. Для Авито и Циан нужен локальный Chrome.
"""
from __future__ import annotations

import base64
import gzip
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request
import webbrowser
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
BUNDLED_CACHE_DIR = os.path.join(ROOT, "data")
# На Vercel каталог проекта только для чтения — свежий кэш живёт в /tmp,
# а снимок data/*.json из репозитория используется как резерв.
CACHE_DIR = os.environ.get("MONETKA_CACHE_DIR") or ("/tmp/monetka" if os.environ.get("VERCEL") else BUNDLED_CACHE_DIR)
os.makedirs(CACHE_DIR, exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 Monetka/1.0"
MSK = timezone(timedelta(hours=3))
LOCK = threading.Lock()
MEM: dict[str, dict] = {}

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


def browser_json_many(urls, expression: str, waits):
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
        proc = subprocess.Popen(
            [
                chrome, "--headless=new", "--disable-gpu", "--no-first-run",
                "--no-default-browser-check", "--window-size=1400,1000",
                f"--remote-debugging-port={port}", f"--user-data-dir={profile}", "about:blank",
            ],
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


def source(name: str, ttl: int, builder):
    """Fetch with TTL cache and last-known-good fallback on disk."""
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
        path = os.path.join(CACHE_DIR, name + ".json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"value": value, "meta": meta}, f, ensure_ascii=False)
        os.replace(tmp, path)
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
        data = http_json("https://www.cbr-xml-daily.ru/daily_json.js", timeout=20)
        vals, d = data["Valute"], data["Date"][:10]
    except Exception:
        xml = http_text("https://www.cbr.ru/scripts/XML_daily.asp", "cp1251")
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
    if not items:
        raise RuntimeError("Нет курсов ЦБ РФ")
    return {"items": items, "date": d, "provider": "ЦБ РФ"}


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


# ---------------------------------------------------------------- deposits (4 источника)
def _walk_ld(obj, out):
    if isinstance(obj, dict):
        if obj.get("@type") in ("InvestmentOrDeposit", "DepositAccount", "BankAccount"):
            out.append(obj)
        for v in obj.values():
            _walk_ld(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_ld(v, out)


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


def build_banki():
    html = http_text("https://www.banki.ru/products/deposits/", timeout=45)
    found: list = []
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            _walk_ld(json.loads(block), found)
        except Exception:
            continue
    items, seen = [], set()
    for o in found:
        try:
            oid = str(o["identifier"])
            if oid in seen:
                continue
            provider = o.get("provider") or {}
            bank = provider.get("name") or "Банк"
            ir = _num((o.get("interestRate") or {}).get("maxValue"))
            apr = _num((o.get("annualPercentageRate") or {}).get("maxValue"))
            amount = o.get("amount") or {}
            name = _clean(o.get("name"))
            if not name or not _deposit_ok(ir or apr):
                continue
            seen.add(oid)
            items.append({
                "id": "banki:" + oid,
                "source": "banki",
                "sourceName": "Банки.ру",
                "name": name,
                "bank": bank,
                "url": o.get("url") or "",
                "logo": provider.get("logo") or (o.get("provider") or {}).get("image") or o.get("logo") or "",
                "rate": float(ir or apr),
                "rateMin": None,
                "apr": float(apr or ir),
                "min": _num(amount.get("minValue")),
                "max": _num(amount.get("maxValue")),
                "currency": amount.get("currency") or "RUB",
                "termDays": parse_term_days(name),
                "note": "",
            })
        except Exception:
            continue
    if not items:
        raise RuntimeError("banki.ru: не удалось разобрать витрину")
    return items


def build_bankiros():
    html = http_text("https://bankiros.ru/deposits", timeout=45)
    found: list = []
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            _walk_ld(json.loads(block), found)
        except Exception:
            continue
    items, seen = [], set()
    for o in found:
        try:
            if o.get("@type") != "DepositAccount":
                continue
            oid = str(o.get("url") or o.get("name"))
            if oid in seen:
                continue
            provider = o.get("provider") or {}
            ir = o.get("interestRate") or {}
            rate = _num(ir.get("maxValue")) or _num(ir.get("minValue"))
            amount = o.get("amount") or {}
            name = _clean(o.get("name"))
            if not name or not _deposit_ok(rate):
                continue
            seen.add(oid)
            items.append({
                "id": "bankiros:" + oid,
                "source": "bankiros",
                "sourceName": "Банкирос",
                "name": name,
                "bank": _clean(provider.get("name")) or "Банк",
                "url": o.get("url") or "",
                "logo": provider.get("image") or "",
                "rate": float(rate),
                "rateMin": _num(ir.get("minValue")),
                "apr": float(rate),
                "min": _num(amount.get("minValue")),
                "max": _num(amount.get("maxValue")),
                "currency": (amount.get("currency") or "RUB").upper(),
                "termDays": parse_term_days(name),
                "note": "",
            })
        except Exception:
            continue
    if not items:
        raise RuntimeError("bankiros.ru: не удалось разобрать витрину")
    return items


def build_finuslugi():
    html = http_text("https://www.finuslugi.ru/vklady/", timeout=45)
    found: list = []
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            _walk_ld(json.loads(block), found)
        except Exception:
            continue
    items, seen = [], set()
    for o in found:
        try:
            if o.get("@type") != "InvestmentOrDeposit":
                continue
            amount = o.get("amount") or {}
            bank = _clean((o.get("provider") or {}).get("name")) or "Банк"
            name = _clean(o.get("name"))
            if name.startswith(bank + "."):
                name = name[len(bank) + 1:].strip()
            name = name.replace("Вклад ", "").strip() or name
            rate = _num(o.get("annualPercentageRate"))
            url = o.get("url") or ""
            if not name or not _deposit_ok(rate) or not url or url in seen:
                continue
            seen.add(url)
            items.append({
                "id": "finuslugi:" + url.rstrip("/").rsplit("-", 1)[-1],
                "source": "finuslugi",
                "sourceName": "Финуслуги",
                "name": name,
                "bank": bank,
                "url": url,
                "logo": "",
                "rate": float(rate),
                "rateMin": None,
                "apr": float(rate),
                "min": _num(amount.get("value")),
                "max": None,
                "currency": amount.get("currency") or "RUB",
                "termDays": parse_term_days(name),
                "note": "",
            })
        except Exception:
            continue
    if not items:
        raise RuntimeError("finuslugi.ru: не удалось разобрать витрину")
    return items


def build_sravni():
    html = http_text("https://www.sravni.ru/vklady/", timeout=45)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("sravni.ru: не найден NEXT_DATA")
    state = json.loads(m.group(1)).get("props", {}).get("initialReduxState", {})
    rows = []
    for q in (state.get("api", {}).get("queries", {}) or {}).values():
        data = (q or {}).get("data") or {}
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            rows.extend(data["data"])
    items, seen = [], set()
    for row in rows:
        try:
            prod = row.get("product") or {}
            bank_data = row.get("bankDetail") or {}
            pid = str(prod.get("id") or "")
            if not pid or pid in seen:
                continue
            rates = [_num(d.get("value")) for d in prod.get("details", []) if d.get("type") == "rate"]
            rates = [r for r in rates if _deposit_ok(r)]
            if not rates:
                continue
            seen.add(pid)
            logos = bank_data.get("logotypes") or {}
            items.append({
                "id": "sravni:" + pid,
                "source": "sravni",
                "sourceName": "Сравни.ру",
                "name": _clean(prod.get("name")) or "Вклад",
                "bank": _clean(bank_data.get("bankName")) or "Банк",
                "url": prod.get("linkToProduct") or "",
                "logo": logos.get("web") or logos.get("square") or "",
                "rate": float(max(rates)),
                "rateMin": float(min(rates)) if len(rates) > 1 else None,
                "apr": float(max(rates)),
                "min": None,
                "max": None,
                "currency": "RUB",
                "termDays": prod.get("seedPeriodDays"),
                "note": "Ставка для суммы 300 000 ₽",
            })
        except Exception:
            continue
    if not items:
        raise RuntimeError("sravni.ru: не найдены вклады")
    return items


def _bank_key(name: str) -> str:
    return re.sub(r"[^а-яёa-z0-9]", "", (name or "").lower().replace("банк", ""))


DEPOSIT_SOURCES = [
    ("banki", "Банки.ру", build_banki, 10800),
    ("bankiros", "Банкирос", build_bankiros, 10800),
    ("finuslugi", "Финуслуги", build_finuslugi, 10800),
    ("sravni", "Сравни.ру", build_sravni, 10800),
]


# ---------------------------------------------------------------- api
def api_market():
    crypto, crypto_meta = source("crypto", 120, build_crypto)
    metals, metals_meta = source("metals", 1800, build_metals)
    fx, fx_meta = source("fx", 1800, build_fx)
    key_rate, key_meta = source("key_rate", 21600, build_key_rate)

    if crypto_meta.get("ok") is False:
        try:
            fallback, fb_meta = source("crypto_fallback", 300, build_crypto_fallback)
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
        "fx": {
            "items": (fx or {}).get("items", []),
            "date": (fx or {}).get("date"),
            "meta": fx_meta,
        },
        "keyRate": {"value": (key_rate or {}).get("value"), "date": (key_rate or {}).get("date"), "meta": key_meta},
        "serverTime": now_msk(),
    }


def _safe_source(name, ttl, builder):
    try:
        return source(name, ttl, builder)
    except Exception as exc:  # noqa: BLE001 - один источник не должен ронять выдачу
        return None, {"ok": False, "error": str(exc)[:300], "stale": False, "updated": None}


def api_deposits():
    items, sources = [], []
    for key, label, builder, ttl in DEPOSIT_SOURCES:
        data, meta = _safe_source("dep_" + key, ttl, builder)
        data = data or []
        items.extend(data)
        sources.append({"key": key, "name": label, "count": len(data), "meta": meta})

    if not items:
        raise RuntimeError("Ни один источник вкладов недоступен")

    logos = {}
    for item in items:
        if item.get("logo"):
            logos.setdefault(_bank_key(item.get("bank")), item["logo"])
    for item in items:
        if not item.get("logo"):
            item["logo"] = logos.get(_bank_key(item.get("bank")), "")

    items.sort(key=lambda x: (-(x.get("rate") or 0), x.get("bank") or ""))
    ok_meta = [s["meta"] for s in sources if s["meta"].get("ok")] or [s["meta"] for s in sources]
    updated = max((m.get("updated") or "" for m in ok_meta), default=None)
    stale = any(m.get("stale") for m in ok_meta)
    key_rate, key_meta = _safe_source("key_rate", 21600, build_key_rate)
    return {
        "items": items,
        "sources": sources,
        "meta": {"ok": any(s["meta"].get("ok") for s in sources), "stale": stale, "updated": updated},
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
# один запрос — 23 карточки, без Chrome и антибота. Национальная выдача и
# крупные города дают по 25 страниц, чего хватает на широкую выборку.
YANDEX_RUSSIA_URL = "https://realty.yandex.ru/rossiya/kupit/kvartira/?rgid=143"
YANDEX_PAGES = 25
YANDEX_CITY_PAGES = 6
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
    sample = avito_items + yandex_items or listings
    russia = None
    if sample:
        # shortcut: медиана и средняя цена м² по выборке карточек, не по всему рынку; перейти на API агрегатора при необходимости.
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


# ---------------------------------------------------------------- http server
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB, **kwargs)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        try:
            if path == "/api/market":
                self.send_json(api_market())
                return
            if path == "/api/deposits":
                self.send_json(api_deposits())
                return
            if path == "/api/realty":
                self.send_json(api_realty())
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
