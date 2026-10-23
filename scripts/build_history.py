"""Refresh bundled chart history snapshots for Vercel/offline fallback."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402

OUT = os.path.join(server.BUNDLED_CACHE_DIR, "history")
os.makedirs(OUT, exist_ok=True)


def save(name, points):
    path = os.path.join(OUT, name + ".json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"points": points}, handle, ensure_ascii=False, separators=(",", ":"))
    print(f"{name}: {len(points)} points")


def main():
    for cg_id, _, symbol, _ in server.COINS:
        try:
            save("crypto_" + cg_id, server._crypto_history(cg_id, symbol, "all"))
        except Exception as exc:  # noqa: BLE001
            print("crypto", cg_id, "ERROR", exc)
    for ticker in ("XAU", "XAG", "XPT", "XPD"):
        try:
            save("metal_" + ticker, server._metal_history(ticker, "all"))
        except Exception as exc:  # noqa: BLE001
            print("metal", ticker, "ERROR", exc)
    for code in server.FX_HISTORY_IDS:
        try:
            save("fx_" + code, server._fx_history_points(code, 730))
        except Exception as exc:  # noqa: BLE001
            print("fx", code, "ERROR", exc)


if __name__ == "__main__":
    main()
