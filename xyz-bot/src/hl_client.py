"""Reader client for the Hyperliquid info API (POST /info).

Read-only. All calls are JSON POSTs to the same endpoint, distinguished by the "type"
field. For the builder-deployed dex, we pass "dex".

Docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals
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

    async def get_meta(self, dex: str) -> dict[str, Any]:
        """universe[] (leverage, marginMode, marginTableId...) + marginTables[]."""
        return await self._post({"type": "meta", "dex": dex})

    async def get_perp_dex_limits(self, dex: str) -> dict[str, Any]:
        """totalOiCap, oiSzCapPerPerp, maxTransferNtl, coinToOiCap (the OI caps)."""
        return await self._post({"type": "perpDexLimits", "dex": dex})

    async def get_perp_dexs(self) -> list[Any]:
        """All builder-deployed perp dexes (no `dex` arg). Each entry has the deployer-level
        config: assetToFundingMultiplier, deployerFeeScale, feeRecipient, subDeployers…"""
        return await self._post({"type": "perpDexs"})

    # Supplementary endpoints (metaAndAssetCtxs, perpsAtOpenInterestCap) intentionally not
    # included: reintroduce them if we wire the pre-OI-increase signal (M6).

    async def aclose(self) -> None:
        await self._client.aclose()
