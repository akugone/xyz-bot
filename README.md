# xyz deployer alert bot

Telegram bot that notifies, in near real-time, **configuration changes of the `xyz` perp DEX**
(trade.xyz) deployed on Hyperliquid via HIP-3: OI cap increases, margin mode, max leverage,
new markets, halts. **Read-only**: it polls the public Hyperliquid info API, diffs state
against the previous snapshot, and posts an alert to a Telegram channel. No transaction
signing, no trading.

> **Live**
> - Telegram channel: **XYZ Deployer Alerts** (via `@tradexyz_alerts_bot`)
> - Public status page: **http://217.65.145.163:8080/** (`/status.json` for monitoring)
> - Runs 24/7 on a Hostinger VPS (systemd).

## Why a snapshot diff?

The HIP-3 deployer does not expose an event feed and is not a readable smart contract — it
signs L1 actions handled by HyperCore. So the bot **polls the deployed state** (`POST /info`,
`dex="xyz"`), builds a **snapshot** (the dex config per coin), and **diffs** it against the
previous snapshot to detect changes. Prices (oracle/mark) are excluded — they change every
~3s and would be noise.

## How it works

```
loop every N seconds (default 5s):
  1. fetch     POST /info  (meta, perpDexLimits) for dex="xyz"
  2. normalize build a per-coin snapshot
  3. diff      vs the previous snapshot (from Postgres) -> typed events
  4. notify    send each new event to Telegram (dedup_key prevents duplicates)
  5. persist   save the new snapshot + heartbeat
```

First run (no baseline) seeds the state **silently** (no alert flood); alerts start from the
second cycle. The daemon is resilient: exponential backoff on API errors, heartbeat, graceful
shutdown on SIGTERM, and an ops alert if the API stays unreachable.

## Repository layout

```
xyz/
├── README.md                  # this file
├── HANDOVER.md                # project status, decisions, open questions
├── ROADMAP.md                 # what's done / what's next
├── STATUS-PAGE.md             # the public status page (access + how it works)
├── xyz-deployer-bot-SPEC.md   # full functional & technical spec
├── learning/                  # background study notes (Hyperliquid / HIP-3)
└── xyz-bot/                    # the application
    ├── src/                   # config, hl_client, snapshot, events, db, messages, telegram, web, main
    ├── tests/                 # 67 tests, ~80% coverage (core logic ~100%); DB tests skip if no DB
    ├── db/schema.sql          # market_state, dex_state, events, bot_status
    └── deploy/                # systemd units + DEPLOY.md + OPS.md
```

## Quickstart (dev)

```bash
cd xyz-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # fill in the values

python -m src.main            # run the daemon (fetch -> diff -> notify -> persist)
python -m src.web             # run the status page (separate service)
```

Without `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`, the bot runs in **dry-run** (alerts are
logged instead of sent). A local Postgres is optional — without `PG_DSN` the bot keeps state
in memory (lost on restart).

## Tests

```bash
cd xyz-bot
pip install -r requirements-dev.txt
python -m pytest tests/ -v
python -m pytest tests/ --cov=src --cov-report=term-missing   # coverage report
```
DB integration tests target a test database; they are **skipped** if it is unreachable
(`TEST_PG_DSN`, default `postgresql://<user>@localhost:5432/xyzbot_test`).

## Deployment & operations

- First deployment: `xyz-bot/deploy/DEPLOY.md` (Ubuntu VPS, Postgres, systemd).
- Day-to-day operations (logs, restart, DB queries, update): `xyz-bot/deploy/OPS.md`.

## Documentation

| Doc | Purpose |
|---|---|
| [HANDOVER.md](HANDOVER.md) | Status, decisions, technical findings, open questions |
| [ROADMAP.md](ROADMAP.md) | Done / next / backlog + API rate-limit analysis |
| [STATUS-PAGE.md](STATUS-PAGE.md) | The public status page |
| [xyz-deployer-bot-SPEC.md](xyz-deployer-bot-SPEC.md) | Full spec (context, endpoints, data model) |
| [xyz-bot/deploy/DEPLOY.md](xyz-bot/deploy/DEPLOY.md) | Deployment runbook |
| [xyz-bot/deploy/OPS.md](xyz-bot/deploy/OPS.md) | Operations cheat sheet |
