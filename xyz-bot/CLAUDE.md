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
Runs as a daemon under **systemd** (`Restart=always`) on an OVH VPS with a local Postgres.

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

## Status
Built and in production (M1–M5 done). To avoid duplication, status is **not** tracked here:
current status → `../HANDOVER.md`, next steps / backlog → `../ROADMAP.md`.

Two findings that explain the code (kept here because they drive implementation choices):
- **marginMode**: only present for isolated markets; **absent = cross** → normalized
  `absent → "normal"` in `snapshot._margin_mode()` so the diff catches the move to cross.
- **halt**: no explicit API field; `isHalted` is read defensively and the `halt`/`unhalt` events are
  **provisional** — to confirm on a real halt.

## Quickstart (dev)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # fill in the values
python -m src.main     # daemon: fetch -> diff -> notify -> persist
python -m src.web      # status page (separate service)
```
