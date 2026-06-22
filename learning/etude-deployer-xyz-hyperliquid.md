# Study of the trade.xyz "deployer" — readable actions for the monitoring bot

> **Historical research note (pre-build).** Superseded by `../xyz-deployer-bot-SPEC.md`, which is the
> canonical reference for the actions, endpoints, and event mapping. Kept for provenance.

**Address studied:** `0x88806a71D74ad0a510b350545C9aE490912F0888`

---

## 1. Main conclusion: it is not an ABI smart contract

`0x8880…0888` is the **HIP-3 deployer of the `xyz` DEX** (trade.xyz) on Hyperliquid — confirmed by
the trade.xyz docs ("HIP-3 Metadata"). trade.xyz is the first HIP-3 deployer and represents the vast
majority of HIP-3 Open Interest (equities, indices/ETFs, tokenized commodities).

Direct consequence for the project: **there is no Solidity ABI to read with `view functions`.** The
deployer doesn't push decodable EVM transactions; it signs **Hyperliquid L1 actions**
(`PerpDeployAction`) processed by HyperCore. So we don't "query the contract" — we monitor two things:

1. **The actions the deployer *can* execute** (the closed list below) → defines the universe of
   possible events.
2. **The resulting deployed state**, read via the **Hyperliquid info API**
   (`POST https://api.hyperliquid.xyz/info`) → where we concretely detect changes, by diffing two
   snapshots.

A database stores the last snapshot and notifies only on the delta (to avoid pinging the same message
twice).

Note: there is also a distinct **Oracle Updater** (`0x1234567890545d1Df9EE64B35Fdd16966e08aCEC`) that
pushes oracle prices — ignore it for monitoring (see §3, noise).

---

## 2. Available deployer actions (`PerpDeployAction`)

Exhaustive list of the variants the xyz deployer can sign (source: Hyperliquid docs "HIP-3 deployer
actions"). The "Ping?" column indicates relevance for the bot.

| Action | What it does | Ping? |
|---|---|---|
| `registerAsset2` / `registerAsset` | Init the dex and/or list a new asset (coin, szDecimals, initial oracle price, marginTableId, margin mode) | **Yes** — new market listed |
| `setOpenInterestCaps` | Change the notional Open Interest cap per asset | **Yes (priority)** — the "OI increase" |
| `setMarginModes` | Change an asset's margin mode: `strictIsolated` ↔ `noCross` | **Yes** — the "isolated → no cross/cross" |
| `setMarginTableIds` | Reassign an asset's margin table (hence max leverage via tiers) | **Yes** — "leverage change" |
| `haltTrading` | Halt / resume trading of an asset (`{coin, isHalted}`) | **Yes** — market halt/resume |
| `setFundingMultipliers` | Per-asset funding multiplier (0 to 10) | Optional — funding impact |
| `setFundingInterestRates` | Interest-rate component of funding (−0.01 to 0.01) | Optional — funding impact |
| `setGrowthModes` | Enable/disable "growth mode" per asset (max 1×/30d) | Optional — rare |
| `setFeeScale` | Dex fee scale (max 1×/30d) | Optional — rare |
| `setFeeRecipient` | Change the fee recipient address | Low — internal |
| `setSubDeployers` | Delegate action permissions to other addresses | Low — governance |
| `setPerpAnnotation` | Perp metadata (category, description, displayName, keywords) | Low — cosmetic |
| `setOracle` | Update the oracle/mark price (≈ every 3s) | **No** — constant noise, exclude |

Possible margin modes (`marginMode` field): `strictIsolated` (non-withdrawable isolated margin),
`noCross` (isolated only), `normal` (cross allowed). Max leverage is bounded to `[1, 50]` and
structured in *margin tiers* (up to 3 tiers: the larger the position, the lower the max leverage).

---

## 3. Mapping: requested event → action → how to detect it

| Requested event | Underlying L1 action | Detection via the info API (field to diff) |
|---|---|---|
| **OI increased** | `setOpenInterestCaps` | `perpDexLimits.coinToOiCap` and `totalOiCap`; also `perpDexs[].assetToStreamingOiCap` |
| **isolated → no cross / cross** | `setMarginModes` | `meta.universe[].marginMode` (`strictIsolated`/`noCross`) |
| **leverage change** | `setMarginTableIds` (+ tables) | `meta.universe[].maxLeverage` and `meta.marginTables[]` |
| **new market** | `registerAsset(2)` | new entry in `meta.universe[]` |
| **halt / resume** | `haltTrading` | to confirm on the API side (see §5 — open point) |

Bot principle: periodic snapshot of the state → comparison with the previous snapshot in the DB →
Telegram ping only on changed fields. **Exclude `oraclePx`/`markPx` from the diff**, otherwise it
pings continuously (updated every ~3s by the oracle updater).

---

## 4. Read endpoints to query (info API)

All via `POST https://api.hyperliquid.xyz/info`, header `Content-Type: application/json`, JSON body.
For the xyz dex, pass `"dex": "xyz"`. Coins are prefixed (`xyz:NVDA`, `xyz:TSLA`, `xyz:XYZ100`…).

**The two core endpoints:**

`perpDexLimits` — the limits, including OI caps (the #1 data point to monitor):
```json
{ "type": "perpDexLimits", "dex": "xyz" }
// → { "totalOiCap", "oiSzCapPerPerp", "maxTransferNtl", "coinToOiCap": [["NVDA","..."],...] }
```

`meta` — the market universe + margin tables (max leverage, margin mode, growth mode per coin):
```json
{ "type": "meta", "dex": "xyz" }
// → universe[]: { name, szDecimals, maxLeverage, marginTableId, marginMode, onlyIsolated, growthMode }
//   marginTables[]: leverage tiers
```

**Supplementary endpoints:**

| Endpoint (`type`) | Provides | Use |
|---|---|---|
| `metaAndAssetCtxs` (`dex:"xyz"`) | universe **+ live context**: `openInterest`, `markPx`, `oraclePx`, `funding`, `dayNtlVlm` | track real OI vs cap |
| `perpsAtOpenInterestCap` (`dex:"xyz"`) | list of perps currently **at their OI cap** | detect pent-up demand (pre-"OI increase") |
| `perpDexs` | all dexs: `deployer`, `oracleUpdater`, `feeRecipient`, `assetToStreamingOiCap`, `assetToFundingMultiplier` | verify deployer identity + streaming caps |
| `perpDexStatus` (`dex:"xyz"`) | the dex's `totalNetDeposit` | global health |
| `allPerpMetas` | all universes + ctx in **a single call** | cheap full snapshot |
| `perpAnnotation` / `perpCategories` / `perpConciseAnnotations` | perp categories/metadata | detect tagged new assets |
| `perpDeployAuctionStatus` | deployment auction status (gas price) | context before a new listing |

---

## 5. Architecture recommendation for the bot

1. **Poll** every N seconds: `meta` + `perpDexLimits` (+ `metaAndAssetCtxs` for real-time OI) for
   `dex:"xyz"`. A single `allPerpMetas` can replace several calls.
2. **Snapshot in the DB** (Postgres): for each coin, store `maxLeverage`, `marginMode`, `oiCap`,
   `isListed`, etc., with a hash of the structural state.
3. **Diff** vs the previous snapshot, ignoring price fields (oracle/mark). Any change of a structural
   field → event.
4. **Formatted Telegram ping** (e.g. "🆕 OI cap NVDA: 5M → 10M", "⚙️ TSLA moves to cross",
   "⛔ AAPL halted"). The processed-events table avoids duplicates.
5. Optional: also push the coins listed in `perpsAtOpenInterestCap` (signal "this will likely be
   increased").

**Open points / to dig into (not resolved by the docs alone):**

- Detecting a `haltTrading` via the info API is not explicit — confirm the exposed field (likely a
  status flag or `isDelisted` in `universe`).
- The info-API **rate limits** under tight polling (validate for the poll frequency).
- Reading the **deployer's actions directly** (not just the resulting state) would require access to
  Hyperliquid block data / a node — the state-diff approach via the API is simpler and sufficient for
  the targeted events.

---

## Sources

- [HIP-3 deployer actions — Hyperliquid Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions)
- [Perpetuals info endpoint — Hyperliquid Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)
- [HIP-3: Builder-deployed perpetuals — Hyperliquid Docs](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals)
- [XYZ Architecture — trade[XYZ] Docs](https://docs.trade.xyz/) (HIP-3 Metadata table: deployer + oracle updater)
