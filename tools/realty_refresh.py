"""Автообновление недвижимости из браузера на этом компьютере.

Яндекс собирается в headless Chrome (домашний IP не получает капчу), Авито — в
отдельном профиле Chrome (антибот пускает только «живой» профиль). Данные
загружаются в кэши VPS через SSH-релей, затем бэкенд перезапускается.

Запуск: python tools/realty_refresh.py [--yandex] [--avito] [--quick]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LOGS = ROOT / "logs"
KEY = Path(r"C:\Users\nmonashkin\Desktop\vps-friend\vps_key")
RELAY = Path(__file__).resolve().parent / "ssh_relay.py"
RELAY_PORTS = (2522, 3022, 8022)
RELAY_PORT = RELAY_PORTS[0]
REMOTE_DATA = "/root/monetka/data"
MSK = timezone(timedelta(hours=3))

YANDEX_CITIES = [
    ("moskva", "Москва", 5), ("sankt-peterburg", "Санкт-Петербург", 5),
    ("novosibirsk", "Новосибирск", 3), ("ekaterinburg", "Екатеринбург", 3),
    ("kazan", "Казань", 3), ("nizhniy-novgorod", "Нижний Новгород", 3),
    ("chelyabinsk", "Челябинск", 3), ("samara", "Самара", 3),
    ("rostov-na-donu", "Ростов-на-Дону", 3), ("krasnodar", "Краснодар", 3),
    ("omsk", "Омск", 2), ("ufa", "Уфа", 2), ("krasnoyarsk", "Красноярск", 2),
    ("voronezh", "Воронеж", 2), ("perm", "Пермь", 2), ("volgograd", "Волгоград", 2),
    ("saratov", "Саратов", 2), ("tyumen", "Тюмень", 2), ("tolyatti", "Тольятти", 2),
    ("izhevsk", "Ижевск", 2), ("barnaul", "Барнаул", 2), ("ulyanovsk", "Ульяновск", 2),
    ("irkutsk", "Иркутск", 2), ("khabarovsk", "Хабаровск", 2), ("yaroslavl", "Ярославль", 2),
    ("vladivostok", "Владивосток", 2), ("makhachkala", "Махачкала", 2), ("tomsk", "Томск", 2),
    ("orenburg", "Оренбург", 2), ("kemerovo", "Кемерово", 2), ("novokuznetsk", "Новокузнецк", 2),
    ("ryazan", "Рязань", 2), ("astrakhan", "Астрахань", 2), ("penza", "Пенза", 2),
    ("naberezhnye-chelny", "Набережные Челны", 2), ("lipetsk", "Липецк", 2),
    ("kirov", "Киров", 2), ("cheboksary", "Чебоксары", 2), ("kaliningrad", "Калининград", 2),
    ("tula", "Тула", 2), ("kursk", "Курск", 2), ("stavropol", "Ставрополь", 2),
    ("ulan-ude", "Улан-Удэ", 2), ("tver", "Тверь", 2), ("magnitogorsk", "Магнитогорск", 2),
    ("sochi", "Сочи", 2), ("ivanovo", "Иваново", 2), ("bryansk", "Брянск", 2),
    ("belgorod", "Белгород", 2), ("surgut", "Сургут", 2), ("vladimir", "Владимир", 2),
    ("nizhniy-tagil", "Нижний Тагил", 2), ("arkhangelsk", "Архангельск", 2),
    ("chita", "Чита", 2), ("kaluga", "Калуга", 2), ("smolensk", "Смоленск", 2),
    ("volzhskiy", "Волжский", 2), ("cherepovets", "Череповец", 2), ("vologda", "Вологда", 2),
    ("saransk", "Саранск", 2), ("yakutsk", "Якутск", 2), ("orel", "Орёл", 2),
    ("krasnogorsk", "Красногорск", 2), ("podolsk", "Подольск", 2), ("khimki", "Химки", 2),
    ("balashikha", "Балашиха", 2), ("korolev", "Королёв", 2), ("mytishchi", "Мытищи", 2),
    ("lyubertsy", "Люберцы", 2), ("odintsovo", "Одинцово", 2), ("domodedovo", "Домодедово", 2),
    ("tambov", "Тамбов", 2), ("kurgan", "Курган", 2), ("grozny", "Грозный", 2),
    ("petrozavodsk", "Петрозаводск", 2), ("murmansk", "Мурманск", 2), ("pskov", "Псков", 2),
    ("velikiy-novgorod", "Великий Новгород", 2), ("kostroma", "Кострома", 2),
    ("nizhnevartovsk", "Нижневартовск", 2), ("novorossiysk", "Новороссийск", 2),
    ("taganrog", "Таганрог", 2), ("shakhty", "Шахты", 2), ("bratsk", "Братск", 2),
    ("syktyvkar", "Сыктывкар", 2), ("nizhnekamsk", "Нижнекамск", 2), ("orsk", "Орск", 2),
]

YANDEX_JS = r"""(() => {
  const CITY = __CITY__;
  const cards = [...document.querySelectorAll('li[data-test="OffersSerpItem"]')];
  const items = [];
  const galleries = {};
  for (const card of cards) {
    const link = card.querySelector('a[href*="/offer/"]');
    if (!link) continue;
    const m = (link.getAttribute('href') || '').match(/\/offer\/(\d+)/);
    if (!m) continue;
    const id = 'yandex:' + m[1];
    const text = card.innerText || '';
    const priceMatch = text.match(/([\d][\d\s\u00a0]{4,})\s*₽/);
    const price = priceMatch ? parseInt(priceMatch[1].replace(/[^\d]/g, ''), 10) : 0;
    if (!price) continue;
    const lines = text.split('\n').map((s) => s.trim()).filter(Boolean);
    const layout = lines.find((l) => /м²/.test(l) && /квартира|студия|комнатная/i.test(l))
      || lines.find((l) => /м²/.test(l)) || lines[0] || '';
    const layoutIdx = lines.indexOf(layout);
    const areaM = layout.match(/([\d.,]+)\s*м²/);
    const roomsM = layout.match(/(\d+)-комнатная/);
    const rooms = /студи/i.test(layout) ? 'Студия' : (roomsM ? roomsM[1] : '');
    const address = lines[layoutIdx + 1] || '';
    const metroIdx = lines.findIndex((l, i) => i > layoutIdx && /мин/.test(l));
    const metro = metroIdx > 1 ? lines[metroIdx - 1] : '';
    const imgs = [...card.querySelectorAll('img')].map((i) => i.getAttribute('src')).filter(Boolean)
      .map((src) => src.startsWith('//') ? 'https:' + src : src)
      .map((src) => src.replace(/\/(app_[a-z_]+)$/, '/app_large'));
    const unique = [...new Set(imgs)];
    if (unique.length) galleries[id] = unique.slice(0, 12);
    const sub = /Жилой квартал|Застройщик|новострой/i.test(text) ? 'Новостройка' : 'Вторичка';
    items.push({ id, source: 'Яндекс', city: CITY, title: layout.replace(/\s*·\s*/g, ', ').slice(0, 160),
      price, area: areaM ? parseFloat(areaM[1].replace(',', '.')) : null, rooms,
      address: address.slice(0, 160), metro: metro.slice(0, 80), sub, sellerType: '', img: unique[0] || '',
      url: 'https://realty.yandex.ru/offer/' + m[1] + '/' });
  }
  return JSON.stringify({ items, galleries });
})()"""

AVITO_JS = r"""(() => {
  const rows = [...document.querySelectorAll('[data-marker="item"]')].map((card) => {
    const img = card.querySelector('img');
    const source = card.querySelector('picture source');
    const srcset = img?.getAttribute('srcset') || source?.getAttribute('srcset') || '';
    const best = srcset.split(',').map((part) => { const [url, size] = part.trim().split(/\s+/); return { url, w: parseInt(size, 10) || 0 }; }).sort((a, b) => b.w - a.w)[0];
    let url = best?.url || img?.getAttribute('data-src') || img?.getAttribute('src') || img?.currentSrc || '';
    if (url.startsWith('//')) url = 'https:' + url;
    return { id: card.dataset.itemId, title: card.querySelector('[itemprop="name"]')?.innerText,
      url: card.querySelector('a[itemprop="url"]')?.href, price: card.querySelector('[itemprop="price"]')?.content,
      img: url, addr: card.querySelector('[data-marker="item-address"]')?.innerText };
  }).filter((row) => row.id && row.url && row.price);
  return JSON.stringify(rows);
})()"""

CIAN_REGIONS = [("2", "Санкт-Петербург"), ("1", "Москва")]
CIAN_PAGES = 25

CIAN_JS = r"""(() => {
  const rows = [...document.querySelectorAll('article[data-name="CardComponent"]')].map((card) => ({
    url: card.querySelector('a[href*="/sale/flat/"]')?.href,
    title: card.querySelector('[data-mark="OfferTitle"]')?.innerText,
    price: card.querySelector('[data-mark="MainPrice"]')?.innerText,
    subtitle: card.querySelector('[data-mark="OfferSubtitle"]')?.innerText,
    img: card.querySelector('img')?.getAttribute('src') || '',
    text: card.innerText
  }));
  return JSON.stringify(rows);
})()"""

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def log(message: str) -> None:
    LOGS.mkdir(exist_ok=True)
    stamp = datetime.now(MSK).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    with open(LOGS / "realty_refresh.log", "a", encoding="utf-8") as file:
        file.write(line + "\n")


def port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def ensure_relay() -> None:
    global RELAY_PORT
    for port in RELAY_PORTS:
        if port_open(port):
            RELAY_PORT = port
            return
        child = subprocess.Popen([sys.executable, str(RELAY), str(port)],
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            if port_open(port):
                RELAY_PORT = port
                return
            if child.poll() is not None:
                break
            time.sleep(0.5)
        if child.poll() is None:
            child.terminate()
    raise RuntimeError("SSH-релей не запустился")


def ssh_client():
    import paramiko

    ensure_relay()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect("127.0.0.1", port=RELAY_PORT, username="root",
                   key_filename=str(KEY), timeout=30, banner_timeout=30)
    return client


def fetch_remote_json(sftp, name: str) -> dict:
    path = f"{REMOTE_DATA}/{name}"
    try:
        with sftp.open(path, "r") as file:
            return json.loads(file.read())
    except Exception:
        return {}


def upload_json(sftp, name: str, payload: dict) -> None:
    tmp = f"{REMOTE_DATA}/{name}.tmp"
    with sftp.open(tmp, "w") as file:
        file.write(json.dumps(payload, ensure_ascii=False))
    sftp.posix_rename(tmp, f"{REMOTE_DATA}/{name}")


def merge_by_id(fresh: list, old: list) -> list:
    old_by_id = {item.get("id"): item for item in old if item.get("id")}
    fresh_ids = {item.get("id") for item in fresh}
    merged = []
    for item in fresh:
        previous = old_by_id.get(item.get("id")) or {}
        if not item.get("img") and previous.get("img"):
            item["img"] = previous["img"]
        merged.append(item)
    merged.extend(item for item in old if item.get("id") not in fresh_ids)
    return merged


def scrape_yandex(quick: bool = False) -> tuple[list, dict]:
    from playwright.sync_api import sync_playwright

    items: list = []
    galleries: dict = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        cities = YANDEX_CITIES[:1] if quick else YANDEX_CITIES
        for slug, city, pages in cities:
            if not quick:
                pages = 4 if slug in ("moskva", "sankt-peterburg") else (2 if pages >= 3 else 1)
            for number in range(1, (1 if quick else pages) + 1):
                url = f"https://realty.yandex.ru/{slug}/kupit/kvartira/" + (f"?page={number}" if number > 1 else "")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    time.sleep(2.5)
                    for _ in range(6):
                        page.mouse.wheel(0, 900)
                        time.sleep(0.3)
                    title = page.title()
                    if "робот" in title.lower():
                        log(f"Яндекс: капча на {city} стр.{number}, прекращаю сбор")
                        raise RuntimeError("captcha")
                    raw = page.evaluate(YANDEX_JS.replace("__CITY__", json.dumps(city, ensure_ascii=False)))
                    data = json.loads(raw)
                    items.extend(data.get("items") or [])
                    galleries.update(data.get("galleries") or {})
                    log(f"Яндекс: {city} стр.{number} — {len(data.get('items') or [])} объявлений")
                except RuntimeError:
                    raise
                except Exception as exc:  # noqa: BLE001 - одна страница не должна ронять обновление
                    log(f"Яндекс: {city} стр.{number} ошибка {type(exc).__name__}")
        browser.close()
    return items, galleries


def scrape_avito(quick: bool = False) -> list:
    from playwright.sync_api import sync_playwright

    profile = Path(os.environ.get("LOCALAPPDATA", str(ROOT))) / "monetka-avito-profile"
    rows: list = []
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(profile), channel="chrome", headless=False,
            user_agent=UA, locale="ru-RU", viewport={"width": 1300, "height": 900},
            args=["--window-position=-2400,-2400", "--window-size=1300,900",
                  "--disable-blink-features=AutomationControlled"],
        )
        context.add_init_script("""
          Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
          Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru'] });
          window.chrome = window.chrome || { runtime: {} };
        """)
        page = context.pages[0] if context.pages else context.new_page()
        pages = 2 if quick else 20
        blocked = False
        for number in range(1, pages + 1):
            url = "https://www.avito.ru/rossiya/kvartiry/prodam" + (f"?p={number}" if number > 1 else "")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(2.5)
                for _ in range(8):
                    page.mouse.wheel(0, 800)
                    time.sleep(0.3)
                if "доступ ограничен" in page.title().lower() or "проверка безопасности" in page.title().lower():
                    log(f"Авито: антибот на стр.{number}, сбор остановлен")
                    blocked = True
                    break
                data = json.loads(page.evaluate(AVITO_JS))
                rows.extend(data)
                log(f"Авито: стр.{number} — {len(data)} карточек")
            except Exception as exc:  # noqa: BLE001
                log(f"Авито: стр.{number} ошибка {type(exc).__name__}")
        context.close()
    return [] if blocked and len(rows) < 40 else rows


def scrape_cian(quick: bool = False) -> list:
    from playwright.sync_api import sync_playwright

    rows: list = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(user_agent=UA, locale="ru-RU", viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        for region, city in CIAN_REGIONS:
            host = "msk" if region == "1" else "spb"
            pages = 2 if quick else CIAN_PAGES
            for number in range(1, pages + 1):
                url = (f"https://{host}.cian.ru/cat.php?deal_type=sale&engine_version=2"
                       f"&offer_type=flat&region={region}")
                if number > 1:
                    url += f"&p={number}"
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    time.sleep(2.5)
                    for _ in range(6):
                        page.mouse.wheel(0, 900)
                        time.sleep(0.25)
                    data = json.loads(page.evaluate(CIAN_JS))
                    if not data:
                        log(f"Циан: {city} стр.{number} пусто, дальше по городу не иду")
                        break
                    rows.extend(data)
                    log(f"Циан: {city} стр.{number} — {len(data)} карточек")
                except Exception as exc:  # noqa: BLE001
                    log(f"Циан: {city} стр.{number} ошибка {type(exc).__name__}")
                    break
        browser.close()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yandex", action="store_true")
    parser.add_argument("--cian", action="store_true")
    parser.add_argument("--bn", action="store_true")
    parser.add_argument("--avito", action="store_true")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    if not args.yandex and not args.cian and not args.bn and not args.avito:
        args.yandex = args.cian = args.bn = True

    log("=== обновление недвижимости начато")

    yandex_items, yandex_galleries = ([], {})
    if args.yandex:
        try:
            yandex_items, yandex_galleries = scrape_yandex(quick=args.quick)
            log(f"Яндекс: собрано {len(yandex_items)} объявлений, галерей {len(yandex_galleries)}")
        except Exception as exc:  # noqa: BLE001
            log(f"Яндекс: сбор прерван — {exc}")

    bn_items = []
    if args.bn:
        try:
            sys.path.insert(0, str(ROOT))
            import server  # noqa: E402 - парсер БН.ру живёт в сервере

            bn_items = server.build_bn()
            log(f"БН.ру: собрано {len(bn_items)} объявлений")
        except Exception as exc:  # noqa: BLE001
            log(f"БН.ру: сбор прерван — {exc}")

    cian_items = []
    if args.cian:
        try:
            rows = scrape_cian(quick=args.quick)
            if rows:
                sys.path.insert(0, str(ROOT))
                import server  # noqa: E402 - парсер Циан живёт в сервере

                cian_items = server._cian_items(rows)
                log(f"Циан: собрано {len(cian_items)} объявлений")
        except Exception as exc:  # noqa: BLE001
            log(f"Циан: сбор прерван — {exc}")

    avito_items = []
    if args.avito:
        try:
            rows = scrape_avito(quick=args.quick)
            if rows:
                sys.path.insert(0, str(ROOT))
                import server  # noqa: E402 - парсер Авито живёт в сервере

                avito_items = server._avito_items(rows)
                log(f"Авито: собрано {len(avito_items)} объявлений")
        except Exception as exc:  # noqa: BLE001
            log(f"Авито: сбор прерван — {exc}")

    if not yandex_items and not cian_items and not avito_items and not bn_items:
        log("нечего загружать, выход")
        return 1

    import paramiko  # noqa: F401 - нужен для ssh_client
    client = ssh_client()
    try:
        sftp = client.open_sftp()
        meta = {"ok": True, "updated": datetime.now(MSK).isoformat(timespec="seconds"),
                "stale": False, "manual": True}
        if yandex_items:
            old = fetch_remote_json(sftp, "realty_yandex.json").get("value") or []
            upload_json(sftp, "realty_yandex.json", {"value": merge_by_id(yandex_items, old), "meta": meta})
            if yandex_galleries:
                images = fetch_remote_json(sftp, "realty_images.json")
                if not isinstance(images, dict):
                    images = {}
                images.update(yandex_galleries)
                upload_json(sftp, "realty_images.json", images)
                log(f"галереи: всего {len(images)} наборов")
        if cian_items:
            old = fetch_remote_json(sftp, "realty_cian.json").get("value") or []
            upload_json(sftp, "realty_cian.json", {"value": merge_by_id(cian_items, old), "meta": meta})
        if bn_items:
            old = fetch_remote_json(sftp, "realty_bn.json").get("value") or []
            upload_json(sftp, "realty_bn.json", {"value": merge_by_id(bn_items, old), "meta": meta})
        if avito_items:
            old = fetch_remote_json(sftp, "realty_avito.json").get("value") or []
            upload_json(sftp, "realty_avito.json", {"value": merge_by_id(avito_items, old), "meta": meta})
        sftp.close()
        client.exec_command("systemctl restart monetka-backend")
        time.sleep(2)
    finally:
        client.close()
    log("=== обновление загружено на VPS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
