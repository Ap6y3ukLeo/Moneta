"""MCP-сервер «Монетки»: карточки банков для внешних ИИ-агентов.

Запуск на VPS: MONETKA_API=http://127.0.0.1:8787 MONETKA_TOKEN=... MCP_TOKEN=... \
    python3 mcp_server.py
Транспорт: Streamable HTTP на 127.0.0.1:8791, путь /mcp.
Авторизация: заголовок Authorization: Bearer <MCP_TOKEN>.
"""
from __future__ import annotations

import hmac
import json
import os
import urllib.error
import urllib.request

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

API = os.environ.get("MONETKA_API", "http://127.0.0.1:8787").rstrip("/")
TOKEN = os.environ.get("MONETKA_TOKEN", "")
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")
PORT = int(os.environ.get("MCP_PORT", "8791"))

mcp = FastMCP(
    "monetka-cards",
    # туннель Cloudflare меняет домен при перезапуске — защиту от DNS rebinding
    # держим на токене в заголовке Authorization
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


def _call(method: str, path: str, payload: dict | None = None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "X-Monetka-Token": TOKEN},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(body).get("error")
        except Exception:  # noqa: BLE001 - тело ошибки может быть не JSON
            message = body[:200]
        raise ValueError(message or f"HTTP {exc.code}") from None


@mcp.tool()
def list_cards(type: str = "") -> list:
    """Список банковских продуктов. type: debit, credit, business или пусто для всех."""
    items = _call("GET", "/api/cards").get("items") or []
    if type:
        items = [item for item in items if item.get("type") == type]
    return [
        {
            "id": item["id"],
            "type": item.get("type"),
            "bank": item.get("bank"),
            "name": item.get("name"),
            "payout": item.get("payout"),
            "pinned": bool(item.get("pinned")),
        }
        for item in items
    ]


@mcp.tool()
def get_card(id: str) -> dict:
    """Полная карточка продукта по id: условия, выгода, ссылка, выплата."""
    items = _call("GET", "/api/cards").get("items") or []
    item = next((entry for entry in items if entry.get("id") == id), None)
    if not item:
        raise ValueError("Продукт не найден")
    return item


@mcp.tool()
def create_card(bank: str, name: str, type: str, payout: int, url: str,
                benefit: str = "", terms: list | None = None, perks: list | None = None) -> dict:
    """Создать карточку.

    type: debit, credit или business.
    payout: сумма клиенту за оформление в рублях.
    terms: список условий, например [{"label": "Кэшбэк", "value": "до 5%"}].
    perks: список преимуществ строками.
    url: ссылка на оформление, обязательно https://.
    """
    payload = {
        "bank": bank, "name": name, "type": type, "payout": payout, "url": url,
        "benefit": benefit, "terms": terms or [], "perks": perks or [],
    }
    return _call("POST", "/api/cards", payload)


@mcp.tool()
def update_card(id: str, fields: dict) -> dict:
    """Изменить поля существующей карточки.

    Разрешены: bank, name, type, payout, benefit, terms, perks, tint.
    Пример fields: {"payout": 3500, "terms": [{"label": "Кэшбэк", "value": "до 7%"}]}.
    """
    return _call("POST", "/api/card_update", {"id": id, "fields": fields})


@mcp.tool()
def delete_card(id: str) -> dict:
    """Удалить карточку, созданную через MCP или бота. Продукты справочника не удаляются."""
    return _call("POST", "/api/card_delete", {"id": id})


@mcp.tool()
def set_card_link(id: str, url: str) -> dict:
    """Поставить реферальную ссылку «Оформить». Пустая строка сбрасывает на исходную."""
    return _call("POST", "/api/links", {"id": id, "url": url})


@mcp.tool()
def pin_card(id: str, pinned: bool = True) -> dict:
    """Закрепить продукт в топе списка (pinned=true) или снять закрепление."""
    return _call("POST", "/api/order", {"id": id, "pinned": pinned})


class TokenAuth(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.url.path in ("/", "/health"):
            return JSONResponse({"ok": True})
        if not MCP_TOKEN:
            return JSONResponse({"error": "MCP_TOKEN not configured"}, status_code=503)
        auth = request.headers.get("authorization") or ""
        if not hmac.compare_digest(auth, f"Bearer {MCP_TOKEN}"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


app = mcp.streamable_http_app()
app.add_middleware(TokenAuth)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="info")
