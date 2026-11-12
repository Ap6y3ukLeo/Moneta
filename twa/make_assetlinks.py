#!/usr/bin/env python3
"""Пишет web/.well-known/assetlinks.json по SHA-256 отпечатку подписи приложения.

Отпечаток печатает `npx @bubblewrap/cli fingerprint` или:
  keytool -list -v -keystore twa/android.keystore -alias monetka | grep SHA256

Пример:
  python twa/make_assetlinks.py "AB:CD:EF:..."
"""
import json
import sys
from pathlib import Path

PACKAGE = "ru.monetka.app"

def main():
    if len(sys.argv) < 2:
        raise SystemExit("укажите SHA-256 отпечаток первым аргументом")
    fingerprint = " ".join(sys.argv[1:]).replace(" ", "").upper()
    if len(fingerprint.replace(":", "")) != 64:
        raise SystemExit("отпечаток должен быть 32 байта в hex, например AB:CD:...")

    target = Path(__file__).resolve().parent.parent / "web" / ".well-known" / "assetlinks.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps([
            {
                "relation": ["delegate_permission/common.handle_all_urls"],
                "target": {
                    "namespace": "android_app",
                    "package_name": PACKAGE,
                    "sha256_cert_fingerprints": [fingerprint],
                },
            }
        ], indent=2) + "\n",
        encoding="utf-8",
    )
    print("written", target)


if __name__ == "__main__":
    main()
