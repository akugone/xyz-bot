# xyz-bot — Alertes deployer trade.xyz (Hyperliquid HIP-3)

Bot Telegram qui notifie en quasi-temps-réel les changements de configuration du DEX de perps `xyz` sur Hyperliquid (OI caps, mode de marge, levier, nouveaux marchés, halts). Lecture seule de l'API + diff d'état + ping Telegram.

## Pourquoi
Le deployer xyz n'expose pas de flux d'événements. On poll l'info API REST d'Hyperliquid, on compare l'état courant au précédent (snapshot), et on alerte sur les changements. Audience : retail + groupes Telegram de la communauté.

> Contexte complet pour l'agent : voir `CLAUDE.md`. Spec détaillée : `../xyz-deployer-bot-SPEC.md`. Concepts : `../concepts-hyperliquid-xyz.md`.

## Démarrage (dev)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # remplir les valeurs
python -m src.main        # M1 : fetch + affiche un snapshot du dex xyz
```

## Structure
```
xyz-bot/
├── CLAUDE.md            # contexte projet (lu par Claude Code)
├── README.md
├── .env.example
├── requirements.txt
├── db/
│   └── schema.sql       # tables market_state, dex_state, events
├── deploy/
│   └── xyz-bot.service  # unit systemd
└── src/
    ├── config.py        # chargement env
    ├── hl_client.py     # client info API Hyperliquid (lecture)
    ├── snapshot.py      # normalisation état → snapshot par coin
    └── main.py          # boucle daemon (diff + notif : à compléter)
```

## État
M0 (cadrage) ✅ · **M1 (lecture) ✅** — client info API + snapshot (93 coins) + tests. Prochaine étape : **M2** (persistance Postgres + moteur de diff). Voir milestones dans `CLAUDE.md`.

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```
