# xyz-bot — trade.xyz deployer alerts (Hyperliquid HIP-3)

Telegram bot that notifies, in near real-time, configuration changes of the `xyz` perp DEX on
Hyperliquid (OI caps, margin mode, leverage, new markets, halts). Read-only API access +
state diff + Telegram ping.

> Overview, "why a snapshot diff", and the docs index live in the **repo root [README](../README.md)**.
> Project context: `CLAUDE.md`. Full spec: `../xyz-deployer-bot-SPEC.md`. Background: `../learning/`.
> This file = app-level dev reference (run, layout, tests).

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
├── assets/
│   ├── fonts/          # bundled Geist + Geist Mono (OFL) — on-brand, deterministic on the VPS
│   └── logos/          # static logo pack, {SYMBOL}.png — built by scripts/fetch_logos.py
├── scripts/
│   └── fetch_logos.py  # one-time: download + validate the equity logo pack
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
    ├── messages.py     # event → parts + flat text (caption)
    ├── cards.py        # event → compact PNG card (logo tile + text)
    ├── telegram.py     # Telegram sender: send() text + send_photo() (with dry-run)
    ├── web.py          # public status page (aiohttp)
    └── main.py         # daemon loop
```

## Alert cards (logos)

Alerts are sent as a compact **card image** (`sendPhoto`): a logo tile on the left + the
event text on the right. The flat text also travels as the photo **caption**, so it stays
copyable and drives the push-notification preview. Rendering is `cards.render_card(ev)`.

- **Logos** are a static pack in `assets/logos/{SYMBOL}.png`, never fetched at runtime.
  Rebuild/refresh it with `python -m scripts.fetch_logos` (run from `xyz-bot/`).
- Only **equities/ETFs** get a real logo. Commodities, forex and indices (GOLD, CL, EUR,
  SP500…) use a colored **category tile** on purpose — a stock-logo API has no entry for
  them, or maps the ticker to the wrong company (GOLD → Barrick, CL → Colgate).
- Bundled fonts (`assets/fonts/`): **Geist** for text + **Geist Mono** for the numeric
  detail line (trade.xyz brand fonts, SIL OFL) — keeps output identical on the Linux VPS.
- If a card ever fails to render/send, the daemon falls back to a plain-text alert — an
  alert is never dropped.

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
