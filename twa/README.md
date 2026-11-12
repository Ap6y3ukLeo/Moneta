# TWA «Монетка»

Приложение-обёртка вокруг сайта `https://moneta-livid-one.vercel.app`.
Внутри — Chrome, снаружи — обычная иконка на телефоне, без адресной строки.

## Что уже готово в репозитории

- `web/manifest.webmanifest` — манифест PWA, подключён в `index.html`.
- `web/icons/*.png` — иконки из `web/logo.svg` (48, 72, 96, 144, 192, 512, maskable 192/512, apple-touch 180).
- `twa/twa-manifest.json` — конфиг для Bubblewrap.
- `twa/make_assetlinks.py` — создаёт `web/.well-known/assetlinks.json` по отпечатку подписи.

## Сборка APK

Нужны Node.js 18+, JDK 17 и Android SDK. Bubblewrap скачает JDK и SDK сам при первом запуске.

```bash
npm i -g @bubblewrap/cli
bubblewrap init --manifest https://moneta-livid-one.vercel.app/manifest.webmanifest
```

При инициализации: имя пакета `ru.monetka.app`, ключ подписи создастся в `twa/android.keystore`
(пароль сохраните — без него не выпустить обновление).

Дальше:

```bash
bubblewrap build
```

На выходе `app-release-signed.apk` и `app-release-bundle.aab` (для Google Play).

## Digital Asset Links

Без него приложение откроет сайт с адресной строкой сверху. Нужен файл
`https://moneta-livid-one.vercel.app/.well-known/assetlinks.json` с SHA-256 подписи.

```bash
bubblewrap fingerprint
python twa/make_assetlinks.py "AB:CD:EF:..."
```

Скрипт создаст `web/.well-known/assetlinks.json`; закоммитить и задеплоить.
Проверка: `https://moneta-livid-one.vercel.app/.well-known/assetlinks.json` должен отдавать JSON.

Отпечаток выпуска в Google Play отличается от локального. Для Play добавьте второй
отпечаток из консоли Play (Release → Setup → App signing) в тот же массив.

## Проверка на телефоне

```bash
adb install app-release-signed.apk
```

Открыть «Монетку»: не должно быть адресной строки и меню Chrome.
Если строка есть — не сошёлся assetlinks.json или отпечаток.

## Уведомления

Включаются в `twa-manifest.json` полем `enableNotifications: true`. Но сама обёртка
уведомления не придумывает: они приходят из сайта через Web Push. Для этого нужен
service worker и VAPID-ключи на сервере (см. `docs/notifications.md`).
