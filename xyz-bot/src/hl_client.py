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

    # --- endpoints d'appoint ---

    async def get_meta_and_asset_ctxs(self, dex: str) -> list[Any]:
        """universe + contexte live : openInterest, markPx, oraclePx, funding."""
        return await self._post({"type": "metaAndAssetCtxs", "dex": dex})

    async def get_perps_at_oi_cap(self, dex: str) -> list[str]:
        """Liste des perps actuellement collés à leur OI cap (signal pré-increase)."""
        return await self._post({"type": "perpsAtOpenInterestCap", "dex": dex})

    async def aclose(self) -> None:
        await self._client.aclose()
