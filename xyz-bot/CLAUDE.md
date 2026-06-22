# CLAUDE.md — project context: "xyz deployer" alert bot (Hyperliquid HIP-3)

> Context file read automatically by Claude Code. It condenses the full spec
> (`../xyz-deployer-bot-SPEC.md`) + the decisions made. If a detail is missing,
> refer to the spec and `../learning/concepts-hyperliquid-xyz.md`.

## Goal
Telegram bot that **notifies, in near real-time, configuration changes** of the `xyz` perp DEX
(trade.xyz) on Hyperliquid. Read-only API access + state diff + Telegram ping. **No** transaction
signing, **no** trading orders.

**Audience**: retail + community Telegram groups (NOT market makers, already equipped). Public
tool. Flagship use case: traders "snipe" OI cap increases.

## Key facts (confirmed)
- xyz deployer: `0x88806a71D74ad0a510b350545C9aE490912F0888` (mainnet). It is **not** an EVM
  contract with an ABI — the deployer signs L1 actions; they can't be read directly.
- **So we poll state via the REST info API and diff between two snapshots.** No WebSocket.
- API: `POST https://api.hyperliquid.xyz/info`, `Content-Type: application/json`, param
  `"dex": "xyz"`. Coins are prefixed (`xyz:NVDA`…).
- **Sub-deployers exist.** → we monitor by state diff (agnostic to the signing address); no need
  to list addresses.
- **Margin transitions**: one-way `strictIsolated → noCross → normal (cross)`, never backwards.
  The bot must also detect the move to cross.

## Core concept: snapshots
The deployer exposes no event feed. We detect changes by comparing current vs previous state.
- **Snapshot** = frozen photo of the dex config at time T, per coin.
- **Tracked fields** (per coin): `max_leverage`, `margin_mode`, `margin_table_id`, `oi_cap`,
  `is_listed`, `is_halted`, `funding_mult`, `growth_mode`; + `total_oi_cap` at the dex level.
- **Exclude `oraclePx`/`markPx`** from the diff (updated every ~3s = noise).
- **Persist in Postgres** (not just in memory): for diffing, dedup, and surviving restarts.
- **First run**: no previous snapshot → store the baseline silently (seed), do NOT ping
  everything as "new". Alerts start from the second cycle.

## Loop (daemon, NOT a cron)
```
loop every N s (target 2–5 s):
  1. fetch     POST /info  (meta, perpDexLimits) dex="xyz"
  2. normalize per-coin snapshot
  3. diff      vs the last snapshot in DB (ignore prices)
  4. on delta  typed event → Telegram ping (dedup_key prevents duplicates)
  5. persist   the new snapshot + heartbeat
  6. sleep N s
```
Runs as a daemon under **systemd** (`Restart=always`) on a Hostinger VPS with a local Postgres.

## Endpoints used
- `perpDexLimits` (dex="xyz") → `totalOiCap`, `coinToOiCap` (the OI caps, data point #1).
- `meta` (dex="xyz") → `universe[]`: `name, maxLeverage, marginTableId, marginMode, onlyIsolated,
  growthMode` + `marginTables[]`.

## Event → diffed field mapping
- OI cap → `perpDexLimits.coinToOiCap`, `totalOiCap`
- Margin mode → `meta.universe[].marginMode` (also catch → `normal`/cross)
- Leverage → `meta.universe[].maxLeverage`
- New market → new entry in `meta.universe[]`
- Delisting / relisting → `meta.universe[].isDelisted` flip (True→listed=delisted, False→listed=relisted). A
  re-listed coin already exists in the universe, so it is NOT a new_market — hence the separate `relisted` event.
- Growth mode → `meta.universe[].growthMode` (enabled/disabled; only fires on a real True↔False flip)
- Halt/resume → mechanism unconfirmed (no explicit API field observed; `isHalted` read defensively)

## Stack & conventions
- Python 3.11+, `httpx` (async), `asyncpg`, `python-dotenv`, `aiohttp` (status page).
- Config via env vars (see `.env.example`). Secrets never committed.
- Code in `src/`, SQL schema in `db/schema.sql`, systemd units in `deploy/`.
- Structured logging + heartbeat. Backoff on API error.

## Milestones (state)
- **M1 Read** ✅ — info API client + readable snapshot (93 coins) + tests.
  - **Finding — marginMode**: `marginMode` only appears in `meta.universe[]` for isolated markets
    (`strictIsolated`/`noCross`, with `onlyIsolated:true`). For a cross market (`normal`) it is
    **absent** → normalized `absent → "normal"` in `snapshot._margin_mode()` so the diff catches
    the move to cross.
  - **Finding — halt**: no explicit halt field in `meta` or `metaAndAssetCtxs`. Only `isDelisted`
    exists (permanent delisting ≠ temporary halt). `isHalted` likely only appears when a market is
    halted (read defensively). To confirm on a real halt.
- **M2 Diff & persistence** ✅ — `src/events.py` (typed events + `dedup_key` + silent seed) and
  `src/db.py` (asyncpg, load/save snapshot, `record_new_events` with `ON CONFLICT DO NOTHING`).
  `run_loop` loads the baseline from Postgres; in-memory fallback if `PG_DSN` is absent.
- **M3 Notifications** ✅ — `src/messages.py` (templates) + `src/telegram.py` (`TelegramNotifier`,
  dry-run). Live sending validated via `@tradexyz_alerts_bot` to the broadcast channel. Public
  messages in English.
- **M4 Daemon & deploy** ✅ — hardened `run_loop` (backoff, heartbeat, graceful SIGTERM). **In
  production** on Hostinger VPS `217.65.145.163` (Ubuntu 24.04), systemd `xyz-bot` active +
  enabled, local Postgres 16. Update: `rsync` of `xyz-bot/` then `systemctl restart`.
- **Public status page** ✅ — separate service `src/web.py` (aiohttp, read-only DB role
  `WEB_PG_DSN`) → `GET /` (HTML) + `/status.json`. Daemon writes a `bot_status` heartbeat each
  cycle. systemd `xyz-bot-web` (port 8080), http://217.65.145.163:8080/.
- **M5 Hardening** ⏳ — rate limits verified (1200 weight/min/IP, ~40% at 5s; floor ~3s).
  **API down/recovered** alert on transition (`API_DOWN_THRESHOLD` → `TELEGRAM_ADMIN_CHAT_ID`,
  not the public channel). End-to-end validated on a real change (controlled baseline test).
  `growth_mode_change` event added. Remaining: confirm halt mechanism. Details in `../ROADMAP.md`.

## Quickstart (dev)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # fill in the values
python -m src.main     # daemon: fetch -> diff -> notify -> persist
python -m src.web      # status page (separate service)
```
