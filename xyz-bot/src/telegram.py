"""Envoi des notifications via l'API Telegram Bot.

`TelegramNotifier.send(text)` poste un message dans le chat cible.
**Mode dry-run** : si activé (ou si le token est absent), on logue le message au lieu
de l'envoyer — permet de développer/tester M3 sans bot réel. Bascule en envoi réel dès
que `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` sont fournis et le dry-run désactivé.
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
        # dry-run forcé OU pas de token/chat → on n'envoie rien pour de vrai.
        self._dry_run = dry_run or not token or not chat_id
        self._client = client or httpx.AsyncClient(timeout=timeout)

    @property
    def dry_run(self) -> bool:
        return self._dry_run

    async def send(self, text: str, chat_id: str | None = None) -> None:
        """Envoie `text`. `chat_id` permet de cibler un autre chat (ex. canal d'alertes ops)."""
        target = chat_id or self._chat_id
        if self._dry_run:
            log.info("[DRY-RUN telegram] → chat=%s\n%s", target, text)
            return
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        resp = await self._client.post(url, json={"chat_id": target, "text": text})
        resp.raise_for_status()

    async def aclose(self) -> None:
        await self._client.aclose()
