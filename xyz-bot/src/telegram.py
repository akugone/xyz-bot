"""Send notifications via the Telegram Bot API.

`TelegramNotifier.send(text)` posts a message to the target chat.
**Dry-run mode**: if enabled (or if the token is missing), the message is logged instead of
sent — lets you develop/test without a real bot. Switches to real sending as soon as
`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` are provided and dry-run is off.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger("xyz-bot.telegram")


class TelegramNotifier:
    def __init__(
        self,
        token: str | None,
        chat_id: str | None,
        dry_run: bool = False,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ):
        self._token = token
        self._chat_id = chat_id
        # forced dry-run OR no token/chat → don't actually send anything.
        self._dry_run = dry_run or not token or not chat_id
        self._client = client or httpx.AsyncClient(timeout=timeout)

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    async def send(self, text: str, chat_id: str | None = None) -> None:
        """Send `text`. `chat_id` targets a different chat (e.g. the ops alerts chat)."""
        target = chat_id or self._chat_id
        if self._dry_run:
            log.info("[DRY-RUN telegram] → chat=%s\n%s", target, text)
            return
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        resp = await self._client.post(url, json={"chat_id": target, "text": text})
        resp.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
