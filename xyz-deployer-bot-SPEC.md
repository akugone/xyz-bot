# Spec & dev plan — "xyz deployer" alert bot (Hyperliquid HIP-3)

> Self-contained document. Meant to be pasted as-is into an agent prompt: it contains all the
> context, technical specs, endpoints, data model, and dev plan. No prior knowledge required.

---

## 1. Context & goal

**Origin.** Request from the trade.xyz team: a Telegram bot that **notifies, in near real-time,
configuration changes** of the `xyz` perp DEX deployed on Hyperliquid.

**Target audience (confirmed).** Not market makers — they already have their own infra to
receive these notifications. The target is **retail** and **other community Telegram groups**. A
third-party bot that **confirms with a clear notification** still has value for that audience.
Positioning: a **public / retail-facing** tool, not an internal MM alert. Flagship use case:
traders "snipe" OI cap increases (e.g. observed on MRVL after an NVDA partnership announcement).

**Goal.** A service that polls the Hyperliquid API, detects state changes of the `xyz` dex, and
sends a formatted Telegram message **exactly once per change** (no duplicates).

**What the project is NOT.** No EVM smart-contract reading, no transaction signing, no trading
orders. Read-only (`POST /info`) + notification.

---

## 2. Confirmed technical facts (sourced)

- The address `0x88806a71D74ad0a510b350545C9aE490912F0888` is the **HIP-3 deployer of the `xyz`
  dex** (trade.xyz), on Hyperliquid **mainnet**. Confirmed by the trade.xyz docs ("HIP-3 Metadata").
- Oracle Updater (distinct address, ignore for monitoring): `0x1234567890545d1Df9EE64B35Fdd16966e08aCEC`.
- **The deployer is not a Solidity contract with an ABI.** It signs **L1 actions**
  (`PerpDeployAction`) handled by HyperCore. We don't read `view functions`; we **poll the
  deployed state via the info API and diff** between two snapshots to detect changes.
- Dex name in the API: `dex = "xyz"`. Coins are prefixed: `xyz:NVDA`, `xyz:TSLA`, `xyz:XYZ100`, etc.
- Base REST endpoint: `POST https://api.hyperliquid.xyz/info`, header `Content-Type: application/json`.

**Sources:**
- HIP-3 deployer actions: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/hip-3-deployer-actions
- Perpetuals info endpoint: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals
- HIP-3 (overview): https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals
- trade.xyz architecture (deployer/oracle metadata): https://docs.trade.xyz/

---

## 3. Deployer actions (`PerpDeployAction`) — reference

Closed list of actions the deployer can sign. The "Tracker" column = default MVP (to be validated).

| Action | Effect | Tracker |
|---|---|---|
| `registerAsset2` / `registerAsset` | Init dex / list a new asset (coin, szDecimals, oraclePx, marginTableId, marginMode) | ✅ new market |
| `setOpenInterestCaps` | Change the notional OI cap per asset | ✅ **priority** (the "OI increase") |
| `setMarginModes` | change margin mode — **one-way** transitions: `strictIsolated → noCross → normal (cross)`, never backwards (confirmed) | ✅ |
| `setMarginTableIds` | `Array<[coin, marginTableId]>` — reassign the margin table (→ max leverage) | ✅ leverage |
| `haltTrading` | `{coin, isHalted}` — halt/resume a market | ✅ |
| `setFundingMultipliers` | `Array<[coin, mult]>` (0–10) | ⚙️ optional |
| `setFundingInterestRates` | `Array<[coin, rate]>` (−0.01..0.01) | ⚙️ optional |
| `setGrowthModes` | `Array<[coin, bool]>` (max 1×/30d) | ✅ implemented (`meta.universe[].growthMode`) |
| `setFeeScale` | fee scale (max 1×/30d) | ❌ |
| `setFeeRecipient` | fee recipient address | ❌ |
| `setSubDeployers` | delegate action permissions to other addresses | ❌ (except governance) |
| `setPerpAnnotation` | metadata (category, description, displayName, keywords) | ❌ cosmetic |
| `setOracle` | oracle/mark price update (~every 3s) | ❌ **noise — exclude from diff** |

Margin modes: `strictIsolated` (non-withdrawable isolated margin), `noCross` (isolated only),
`normal` (cross allowed). **Confirmed transitions: a market only moves in the loosening
direction — `strictIsolated → noCross → normal (cross)`, never backwards.** The bot must also
detect the move to `normal` (cross), not just strict↔noCross. Since we diff the `marginMode`
state field (which can take any value), detection is robust regardless of the exact action-side
mechanism. Max leverage ∈ [1, 50], structured in *margin tiers* (≤ 3 tiers, leverage decreasing
with position size).

**Sub-deployers (confirmed):** sub-deployers exist — addresses other than `0x8880…0888` can
modify the dex config. Implication: **monitoring by state diff (not by signing address) remains
the right approach**, since we capture the change regardless of which address signed it. No need
to enumerate the sub-deployers for monitoring.

---

## 4. Read endpoints (info API) & mapping

All: `POST https://api.hyperliquid.xyz/info`, JSON body, `"dex": "xyz"` for the target dex.

### Core endpoints (to poll)

**`perpDexLimits`** — the limits, including OI caps (data point #1):
```json
// request
{ "type": "perpDexLimits", "dex": "xyz" }
// response
{ "totalOiCap": "...", "oiSzCapPerPerp": "...", "maxTransferNtl": "...",
  "coinToOiCap": [["xyz:NVDA","..."], ["xyz:TSLA","..."]] }
```

**`meta`** — market universe + margin tables:
```json
// request
{ "type": "meta", "dex": "xyz" }
// response (universe[] excerpt)
{ "universe": [
    { "name":"xyz:NVDA", "szDecimals":3, "maxLeverage":10, "marginTableId":10,
      "onlyIsolated":true, "marginMode":"strictIsolated", "growthMode":"enabled",
      "lastGrowthModeChangeTime":"..." } ],
  "marginTables": [ [10, { "description":"...", "marginTiers":[ {"lowerBound":"0.0","maxLeverage":10} ] }] ] }
```

### Supplementary endpoints

| `type` | Provides | Use |
|---|---|---|
| `metaAndAssetCtxs` (`dex`) | universe + live ctx: `openInterest`, `markPx`, `oraclePx`, `funding`, `dayNtlVlm` | real OI vs cap |
| `perpsAtOpenInterestCap` (`dex`) | list of perps sitting at their OI cap | pre-"OI increase" signal |
| `perpDexs` (no `dex`) | all dexs: `deployer`, `oracleUpdater`, `feeRecipient`, `assetToStreamingOiCap`, `assetToFundingMultiplier` | identity check + streaming caps |
| `perpDexStatus` (`dex`) | `totalNetDeposit` | global health |
| `allPerpMetas` | all universes + ctx in one call | cheap full snapshot |
| `perpAnnotation` / `perpCategories` / `perpConciseAnnotations` | metadata/categories | tagged new assets |

### Event → action → diffed field mapping

| Event | L1 action | Detected field |
|---|---|---|
| OI cap changed | `setOpenInterestCaps` | `perpDexLimits.coinToOiCap`, `totalOiCap` |
| Margin mode changed | `setMarginModes` | `meta.universe[].marginMode` (also detect → `normal`/cross) |
| Max leverage changed | `setMarginTableIds` | `meta.universe[].maxLeverage` + `meta.marginTables[]` |
| New market | `registerAsset(2)` | new entry in `meta.universe[]` |
| Halt / resume | `haltTrading` | **TO VERIFY** — API status field (likely a flag; otherwise infer via ctx disappearance / `isDelisted`) |

---

## 5. Architecture

**Pattern: long-running daemon** (NOT a cron). Reasons: cron has ≥ 1 min granularity (too slow)
and loses state between runs (we need the previous snapshot). The process runs continuously
under **systemd** (auto-restart on crash).

```
┌─────────────────────────────────────────────┐
│  systemd service (micro VM)                  │
│                                              │
│   loop every N s (target 2–5 s):             │
│     1. fetch  : POST /info (meta, perpDexLimits) dex="xyz"
│     2. normalize : extract structural fields per coin
│     3. diff   : vs last snapshot in DB (IGNORE oraclePx/markPx)
│     4. on delta : compose message + INSERT event (idempotency) + send Telegram
│     5. persist the new snapshot
│     6. sleep N s                             │
└──────────────┬───────────────────────────────┘
               │
        PostgreSQL
               │
        Telegram Bot API (target channel)
```

**REST polling confirmed**: no WebSocket feed for these config changes → the architecture is
**short polling**, no WS fallback to plan for.

### Reactivity
Latency ≈ poll interval. The oracle updates ~every 3s, so a **2–5s** poll gives near real-time for
config changes. Validate the info-API **rate limits** before going too low.

---

## 6. Data model (PostgreSQL)

```sql
-- Current state per (dex, coin): basis for the diff
CREATE TABLE market_state (
  dex            TEXT NOT NULL,
  coin           TEXT NOT NULL,
  max_leverage   INT,
  margin_mode    TEXT,           -- strictIsolated | noCross | normal
  margin_table_id INT,
  oi_cap         NUMERIC,        -- notional cap (coinToOiCap)
  is_listed      BOOLEAN DEFAULT TRUE,
  is_halted      BOOLEAN,
  funding_mult   NUMERIC,
  growth_mode    BOOLEAN,
  updated_at     TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (dex, coin)
);

-- Dex-wide limits
CREATE TABLE dex_state (
  dex          TEXT PRIMARY KEY,
  total_oi_cap NUMERIC,
  updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Journal of detected events = anti-duplicate idempotency
CREATE TABLE events (
  id          BIGSERIAL PRIMARY KEY,
  dex         TEXT NOT NULL,
  coin        TEXT,
  event_type  TEXT NOT NULL,    -- oi_cap_change | margin_mode_change | leverage_change | new_market | halt | ...
  old_value   TEXT,
  new_value   TEXT,
  dedup_key   TEXT UNIQUE,      -- e.g. sha256(dex|coin|event_type|new_value) → INSERT ON CONFLICT DO NOTHING
  notified_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT now()
);
```

Anti-duplicate logic: compute `dedup_key` per event; `INSERT ... ON CONFLICT (dedup_key) DO
NOTHING`; only send the Telegram message if the insert actually created a row.

---

## 7. Telegram message format (proposal)

```
🟢 OI cap increased — xyz:NVDA
5,000,000 → 10,000,000 USDC
{timestamp UTC}

⚙️ Margin mode — xyz:TSLA
noCross → normal (cross enabled)

📈 Max leverage — xyz:AAPL
10x → 20x

🆕 New market listed — xyz:META
leverage 10x · strictIsolated · OI cap 2,000,000

⛔ Trading halted — xyz:AMZN   /   ✅ Trading resumed — xyz:AMZN
```
To confirm: target channel, level of detail, whether to send one message per coin or a grouped
message when an action touches several coins.

---

## 8. Stack & deployment

- **Language**: Python 3.11+ (httpx + asyncio). Python recommended for polling/async simplicity.
- **DB**: PostgreSQL.
- **Hosting**: a micro Linux VM, **systemd** service (`Restart=always`), deployed over SSH.
- **Config via env vars**: `HL_API_URL`, `DEX_NAME=xyz`, `POLL_INTERVAL_SEC`, `PG_DSN`,
  `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- **Secrets**: never in clear text in the repo; `.env` not committed / secrets manager.
- **Observability**: structured logging + a heartbeat (e.g. a daily "still alive" ping or metric)
  to know whether the service is running.

### Example systemd unit
```ini
[Unit]
Description=xyz deployer alert bot
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 /opt/xyz-bot/main.py
EnvironmentFile=/opt/xyz-bot/.env
Restart=always
RestartSec=5
User=xyzbot

[Install]
WantedBy=multi-user.target
```

---

## 9. Development plan (milestones)

1. **M0 — Scoping**: ✅ events / audience / REST / sub-deployers settled (see §10). Still to settle:
   exact Telegram channel, target latency, rate limits. Get DB + VM access.
2. **M1 — Read**: info API client; fetch + parse `meta`, `perpDexLimits` for `dex="xyz"`. Log a
   readable snapshot.
3. **M2 — Persistence & diff**: SQL schema; per-coin normalization; diff engine (ignoring
   oracle/mark) producing a list of typed events.
4. **M3 — Notifications**: Telegram Bot API integration; message templates; idempotency via `dedup_key`.
5. **M4 — Daemon & deployment**: async loop + backoff on API error; systemd unit; SSH deployment;
   logs + heartbeat.
6. **M5 — Hardening**: rate-limit handling, reconnections, alert if the API is down, test on a real
   change (or simulated by injecting a fake previous snapshot).
7. **M6 (optional)**: multi-dex extension; second Telegram channel; richer "pre-OI-increase" signal.

---

## 10. Settled points & remaining risks

**Settled:**
- **Margin transitions**: one-way `strictIsolated → noCross → normal (cross)`, never backwards.
  → the bot also detects moves to cross.
- **REST polling only**: no WebSocket for these changes → short polling, final.
- **Audience**: retail + other Telegram groups (not MMs, already equipped). Public tool.
- **Sub-deployers**: they exist. → monitor by **state diff** (agnostic to the signing address);
  no need to list the sub-deployers.

**Risks / still-open points:**
- **Halt detection**: API field unconfirmed (verify on real data).
- **Rate limits** of the info API under tight polling.
- **Target Telegram channel** + target latency (to finalize).
