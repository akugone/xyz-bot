"""Client de lecture de l'info API Hyperliquid (POST /info).

Lecture seule. Tous les appels sont des POST JSON vers le même endpoint,
différenciés par le champ "type". Pour le dex builder-deployed, on passe "dex".

Doc : https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals
"""
from __future__ import annotations

from typing import Any

import httpx

from .config import config


class HyperliquidClient:
    def __init__(self, api_url: str | None = None, timeout: float = 10.0):
        self._url = api_url or config.hl_api_url
        self._client = httpx.AsyncClient(timeout=timeout)

    async def _post(self, payload: dict[str, Any]) -> Any:
        resp = await self._client.post(
            self._url, json=payload, headers={"Content-Type": "application/json"}
        )
        resp.raise_for_status()
        return resp.json()

    # --- endpoints cœur ---

    async def get_meta(self, dex: str) -> dict[str, Any]:
        """universe[] (levier, marginMode, marginTableId...) + marginTables[]."""
        return await self._post({"type": "meta", "dex": dex})

    async def get_perp_dex_limits(self, dex: str) -> dict[str, Any]:
        """totalOiCap, oiSzCapPerPerp, maxTransferNtl, coinToOiCap (les OI caps)."""
        return await self._post({"type": "perpDexLimits", "dex": dex})

    # Endpoints d'appoint non encore utilisés (metaAndAssetCtxs, perpsAtOpenInterestCap)
    # retirés volontairement : à réintroduire si on branche le signal pré-OI-increase (M6).

    async def aclose(self) -> None:
        await self._client.aclose()
