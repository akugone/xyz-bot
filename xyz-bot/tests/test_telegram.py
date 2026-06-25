"""TelegramNotifier tests — dry-run (no network) vs real sending (httpx mocked)."""
import asyncio

import httpx

from src.telegram import TelegramNotifier


def test_dry_run_when_no_token():
    """Without a token, the notifier is forced into dry-run (sends nothing)."""
    n = TelegramNotifier(token=None, chat_id="123", dry_run=False)
    assert n.dry_run is True
    asyncio.run(n.send("hello"))  # must not raise (no network call)
    asyncio.run(n.aclose())


def test_dry_run_explicit():
    n = TelegramNotifier(token="T", chat_id="123", dry_run=True)
    assert n.dry_run is True
    asyncio.run(n.send("hello"))
    asyncio.run(n.aclose())


def test_real_send_posts_to_telegram_api():
    """With token + chat and dry-run off: POST to the Telegram API with the right payload."""
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


def test_send_photo_dry_run_no_network():
    """No token → dry-run; send_photo must not hit the network."""
    n = TelegramNotifier(token=None, chat_id="123", dry_run=False)
    asyncio.run(n.send_photo(b"\x89PNG fake", caption="hi"))
    asyncio.run(n.aclose())


def test_send_photo_posts_multipart_to_sendphoto():
    """With token + chat: POST to sendPhoto with the caption and a photo file part."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers.get("content-type", "")
        captured["body"] = request.content  # raw multipart bytes
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    n = TelegramNotifier(token="ABC123", chat_id="-100999", dry_run=False, client=client)

    async def scenario():
        await n.send_photo(b"\x89PNG\r\n\x1a\nDATA", caption="🟢 caption")
        await n.aclose()

    asyncio.run(scenario())

    assert captured["url"] == "https://api.telegram.org/botABC123/sendPhoto"
    assert "multipart/form-data" in captured["content_type"]
    assert b"-100999" in captured["body"]
    assert b"\x89PNG" in captured["body"]


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
