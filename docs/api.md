# API «Монетки»

Четыре эндпоинта. Токен в заголовке, без него 401.

```http
X-Monetka-Token: <token>
```

Адрес: `https://moneta-livid-one.vercel.app`. Резервный: туннель на VPS, его адрес меняется после перезапуска.

Ошибки: `{"error": "текст"}`, коды 400, 404, 502. Суммы в рублях, если в `unit` не написано другое.

## Данные по категории

```http
GET /api/bot?category=crypto&limit=10
```

`category`: `crypto`, `stocks`, `metals`, `fx`, `deposits`, `realty`. Без неё вернёт список категорий.
`limit`: 1..50, по умолчанию 10.

```json
{
  "category": "crypto",
  "text": "Криптовалюта\n\nBTC — $76 254,10 (-2,01%)\n\nОбновлено: 06.11.2026 11:58",
  "items": [{"symbol": "BTC", "name": "Bitcoin", "price": 76254.1, "change24h": -2.01}],
  "updated": "06.11.2026 11:58"
}
```

`text` можно сразу отправить в чат. `items` берите, если нужна своя разметка.

Поля элементов:

| category | поля |
|---|---|
| crypto | symbol, name, price (USD), change24h |
| stocks | ticker, name, price (₽), change24h |
| metals | code, name, price (₽/г), change24h |
| fx | code, name, value (₽), change24h, source |
| deposits | bank, name, rate, termText, min, url |
| realty | id, source, city, title, price, area, url |

## История для своих графиков

```http
GET /api/history?kind=crypto&id=bitcoin&range=7d
```

`kind`: `crypto`, `stock`, `metal`, `fx`. Можно не указывать, определится по `id`.
`id`: id или тикер (`bitcoin` или `btc`, `SBER` или `sber`, `XAU`, `USD`).
`range`: `1d`, `7d`, `1m`, `3m`, `1y`, `all`.

```json
{
  "id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "unit": "USD",
  "points": [
    {"t": "2026-10-30T03:00:00+03:00", "c": 81753.4},
    {"t": "2026-10-31T03:00:00+03:00", "c": 82625.4}
  ]
}
```

`t`: московское время. `c`: цена закрытия.

Идентификаторы:

- crypto: `bitcoin`, `ethereum`, `solana`, `binancecoin`, `ripple`, `cardano`, `dogecoin`, `sui`, `tron`, `avalanche-2`, `chainlink`, `tether`
- stock: тикер MOEX (`SBER`, `GAZP`, `LKOH`, `YDEX`)
- metal: `XAU`, `XAG`, `XPT`, `XPD`
- fx: `USD`, `EUR`, `CNY`, `GBP`

## График картинкой

```http
GET /api/chart?id=btc&range=7d
```

Параметры те же. Ответ: `image/png`, 1200 × 630, 70–90 КБ, 0,3–1 с.

На картинке: тикер и название, цена крупно, изменение за период, линия с заливкой, сетка, подписи дат. Цвета сайта: зелёный при росте, красный при падении.

```bash
curl -H "X-Monetka-Token: $TOKEN" \
  "https://moneta-livid-one.vercel.app/api/chart?id=btc&range=7d" -o btc.png
```

## Карточка категории

```http
GET /api/card?category=deposits&limit=12
```

`category` обязателен: `crypto`, `stocks`, `metals`, `fx`, `deposits`, `realty`.
`limit`: 1..20, по умолчанию 10.

Ответ: `image/png`, ширина 1200, высота зависит от числа строк. Внутри заголовок, дата обновления и строки «название, значение, примечание». Для недвижимости сначала сводка Москвы и России, потом объявления.

Этим же эндпоинтом пользуется бот: одна карточка на категорию.

## Примеры

Python, сохранить и отправить в Telegram:

```python
png = requests.get(f"{API}/api/chart", params={"id": "btc", "range": "7d"},
                   headers={"X-Monetka-Token": TOKEN}, timeout=60).content
open("btc.png", "wb").write(png)

requests.post(f"https://api.telegram.org/bot{BOT}/sendPhoto",
              data={"chat_id": chat_id, "caption": "BTC за неделю"},
              files={"photo": ("btc.png", png, "image/png")}, timeout=60)
```

JavaScript, показать картинку:

```js
const url = new URL(`${API}/api/chart`);
url.search = new URLSearchParams({ id: "btc", range: "7d" });
const blob = await (await fetch(url, { headers: { "X-Monetka-Token": TOKEN } })).blob();
img.src = URL.createObjectURL(blob);
```

JavaScript, только цифры:

```js
const { text, items } = await (await fetch(`${API}/api/bot?category=deposits`,
  { headers: { "X-Monetka-Token": TOKEN } })).json();
```

## Кэш

Курсы, акции, крипта и металлы обновляются раз в 5 минут, вклады раз в сутки, недвижимость раз в 12 часов. График можно кэшировать на 5 минут.
