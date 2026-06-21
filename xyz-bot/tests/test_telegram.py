"""Tests M3 : TelegramNotifier — dry-run (aucun réseau) vs envoi réel (httpx mocké)."""
import asyncio

import httpx

from src.telegram import TelegramNotifier


def test_dry_run_when_no_token():
    """Sans token, le notifier est forcément en dry-run (n'envoie rien)."""
    n = TelegramNotifier(token=None, chat_id="123", dry_run=False)
    assert n.dry_run is True
    asyncio.run(n.send("hello"))  # ne doit pas lever (pas d'appel réseau)
    asyncio.run(n.aclose())


def test_dry_run_explicit():
    n = TelegramNotifier(token="T", chat_id="123", dry_run=True)
    assert n.dry_run is True
    asyncio.run(n.send("hello"))
    asyncio.run(n.aclose())


def test_real_send_posts_to_telegram_api():
    """Avec token + chat et dry-run off : POST vers l'API Telegram avec le bon payload."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    n = TelegramNotifier(token="ABC123", chat_id="-100999", dry_run=False, client=client)
    assert n.dry_run is False

    async def scenario():
        await n.send("🟢 test")
        await n.aclose()

    asyncio.run(scenario())

    assert captured["url"] == "https://api.telegram.org/botABC123/sendMessage"
    assert captured["body"] == {"chat_id": "-100999", "text": "🟢 test"}


def test_real_send_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "Bad Request"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    n = TelegramNotifier(token="ABC", chat_id="1", dry_run=False, client=client)

    async def scenario():
        raised = False
        try:
            await n.send("x")
        except httpx.HTTPStatusError:
            raised = True
        await n.aclose()
        return raised

    assert asyncio.run(scenario()) is True
