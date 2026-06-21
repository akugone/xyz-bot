# xyz-bot — trade.xyz deployer alerts (Hyperliquid HIP-3)

Telegram bot that notifies, in near real-time, configuration changes of the `xyz` perp DEX on
Hyperliquid (OI caps, margin mode, leverage, new markets, halts). Read-only API access +
state diff + Telegram ping.

> Project overview & docs index: see the **repo root [README](../README.md)**.
> Project context: `CLAUDE.md`. Full spec: `../xyz-deployer-bot-SPEC.md`. Background: `../learning/`.

## Why
The xyz deployer exposes no event feed. We poll Hyperliquid's REST info API, compare current
state to the previous one (snapshot), and alert on changes. Audience: retail + community
Telegram groups.

## Quickstart (dev)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env      # fill in the values
python -m src.main        # daemon: fetch -> diff -> notify -> persist
python -m src.web         # status page (separate service)
```

## Layout
```
xyz-bot/
├── CLAUDE.md            # project context
├── README.md
├── .env.example
├── requirements.txt / requirements-dev.txt
├── db/
│   └── schema.sql       # market_state, dex_state, bot_status, events
├── deploy/
│   ├── xyz-bot.service      # daemon systemd unit
│   ├── xyz-bot-web.service  # status page systemd unit
│   ├── DEPLOY.md            # deployment runbook
│   └── OPS.md               # operations cheat sheet
└── src/
    ├── config.py       # env loading
    ├── hl_client.py    # Hyperliquid info API client (read)
    ├── snapshot.py     # state → per-coin snapshot normalization
    ├── events.py       # diff engine (typed events + dedup_key)
    ├── db.py           # Postgres persistence (asyncpg)
    ├── messages.py     # event → Telegram message templates
    ├── telegram.py     # Telegram sender (with dry-run)
    ├── web.py          # public status page (aiohttp)
    └── main.py         # daemon loop
```

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```
Persistence tests (`test_db.py`) target a test Postgres; they are **skipped** if it is
unavailable. DSN via `TEST_PG_DSN` (default: `postgresql://<user>@localhost:5432/xyzbot_test`).

## Local Postgres (dev)
```bash
brew services start postgresql@15      # or docker
createdb xyzbot                        # dev database
createdb xyzbot_test                   # test database
export PG_DSN="postgresql://<user>@localhost:5432/xyzbot"
python -m src.main
```

## Deployment & operations
See `deploy/DEPLOY.md` (first deployment) and `deploy/OPS.md` (day-to-day operations).
