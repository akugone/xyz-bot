"""HyperliquidClient tests — request payloads and parsing (httpx mocked, no network)."""
import asyncio

import httpx

from src.hl_client import HyperliquidClient


def _client_with(handler):
    """A HyperliquidClient whose HTTP transport is the given mock handler."""
    c = HyperliquidClient()
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # noqa: SLF001
    return c


def test_get_meta_sends_right_payload_and_parses():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"universe": [{"name": "xyz:NVDA"}]})

    c = _client_with(handler)

    async def scenario():
        out = await c.get_meta("xyz")
        await c.aclose()
        return out

    out = asyncio.run(scenario())
    assert captured["url"] == "https://api.hyperliquid.xyz/info"
    assert captured["body"] == {"type": "meta", "dex": "xyz"}
    assert out["universe"][0]["name"] == "xyz:NVDA"


def test_get_perp_dex_limits_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"totalOiCap": "7000000000.0", "coinToOiCap": []})

    c = _client_with(handler)

    async def scenario():
        out = await c.get_perp_dex_limits("xyz")
        await c.aclose()
        return out

    out = asyncio.run(scenario())
    assert captured["body"] == {"type": "perpDexLimits", "dex": "xyz"}
    assert out["totalOiCap"] == "7000000000.0"


def test_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limited"})

    c = _client_with(handler)

    async def scenario():
        raised = False
        try:
            await c.get_meta("xyz")
        except httpx.HTTPStatusError:
            raised = True
        await c.aclose()
        return raised

    assert asyncio.run(scenario()) is True
