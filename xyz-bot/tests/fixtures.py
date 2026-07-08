"""Fixtures inspired by real Hyperliquid info API responses (dex=xyz).

Captured on 2026-06-21 via `meta` / `perpDexLimits`. Reduced to a representative sample
of the cases that matter for the diff:
  - isolated `noCross` market (HOOD): marginMode present + onlyIsolated
  - isolated `strictIsolated` market (MINIMAX)
  - cross `normal` market (XYZ100): marginMode ABSENT → must be normalized to "normal"
  - delisted market (DXY): isDelisted=True → is_listed=False
"""

META_RESPONSE = {
    "universe": [
        {
            "szDecimals": 3, "name": "xyz:HOOD", "maxLeverage": 10,
            "marginTableId": 10, "onlyIsolated": True, "marginMode": "noCross",
            "growthMode": "enabled",
            "lastGrowthModeChangeTime": "2025-11-23T17:37:10.033211662",
        },
        {
            "szDecimals": 3, "name": "xyz:MINIMAX", "maxLeverage": 10,
            "marginTableId": 10, "onlyIsolated": True, "marginMode": "strictIsolated",
            "growthMode": "enabled",
            "lastGrowthModeChangeTime": "2025-11-23T17:37:10.033211662",
        },
        {
            # cross-enabled: no marginMode, no onlyIsolated
            "szDecimals": 4, "name": "xyz:XYZ100", "maxLeverage": 30,
            "marginTableId": 30, "growthMode": "enabled",
            "lastGrowthModeChangeTime": "2025-11-23T17:37:10.033211662",
        },
        {
            "szDecimals": 2, "name": "xyz:DXY", "maxLeverage": 20,
            "marginTableId": 20, "onlyIsolated": True, "marginMode": "noCross",
            "isDelisted": True, "growthMode": "enabled",
            "lastGrowthModeChangeTime": "2025-11-23T17:37:10.033211662",
        },
    ],
    "marginTables": [
        [10, {"description": "", "marginTiers": [{"lowerBound": "0.0", "maxLeverage": 10}]}],
        [30, {"description": "", "marginTiers": [{"lowerBound": "0.0", "maxLeverage": 30}]}],
    ],
    "collateralToken": 0,
}

PERP_DEX_LIMITS_RESPONSE = {
    "totalOiCap": "7000000000.0",
    "oiSzCapPerPerp": "...",
    "maxTransferNtl": "...",
    "coinToOiCap": [
        ["xyz:HOOD", "50000000.0"],
        ["xyz:MINIMAX", "25000000.0"],
        ["xyz:XYZ100", "100000000.0"],
        ["xyz:DXY", "25000000.0"],
    ],
}

# `perpDexs` returns ALL dexes; the xyz entry carries the deployer-level config.
# Reduced here to the funding multiplier (the field we track).
PERP_DEXS_RESPONSE = [
    None,  # index 0 is the empty/native dex in the real response
    {
        "name": "xyz",
        "fullName": "XYZ",
        "deployer": "0x88806a71d74ad0a510b350545c9ae490912f0888",
        "deployerFeeScale": "1.0",
        "assetToFundingMultiplier": [
            ["xyz:HOOD", "0.5"],
            ["xyz:MINIMAX", "0.5"],
            ["xyz:XYZ100", "0.5"],
            ["xyz:DXY", "0.5"],
        ],
    },
]
XYZ_PERP_DEX = PERP_DEXS_RESPONSE[1]
