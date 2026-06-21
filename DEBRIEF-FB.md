# Débrief projet — Bot d'alertes deployer `xyz` (Hyperliquid HIP-3)

> Document **vivant**, complété au fil des milestones. Sert de support au point avec fb.
> Archive du cadrage initial : `questions-pour-fb.md`. Spec complète : `xyz-deployer-bot-SPEC.md`.
> Page de statut publique : `STATUS-PAGE.md`. Exploitation : `xyz-bot/deploy/OPS.md`. Suite prévue : `ROADMAP.md`.
> Dernière mise à jour : **2026-06-21**.

---

## 1. Avancement (par milestone)

| Milestone | État | Note |
|---|---|---|
| M0 — Cadrage | ✅ | events / audience / REST / sub-deployers tranchés avec fb |
| **M1 — Lecture** | ✅ | client info API + snapshot (93 coins) + 8 tests verts |
| **M2 — Diff & persistance** | ✅ | moteur de diff + persistance Postgres (asyncpg). Baseline survit au redémarrage (seed seulement si base vide). 25 tests verts, validé en live |
| **M3 — Notifications** | ✅ | templates + envoi Telegram, **envoi réel validé** sur le canal de broadcast « XYZ Deployer Alerts » (@tradexyz_alerts_bot, bot admin) |
| **M4 — Daemon & déploiement** | ✅ | **déployé en prod** sur VPS Hostinger (Ubuntu 24.04), systemd actif + au boot, Postgres locale, envoi réel Telegram. Tourne 24/7 |
| M5 — Durcissement | ⬜ | rate limits, reconnections, alerte API down |

---

## 2. Décisions tranchées

- **Hébergement = VPS Hostinger** (compte de Martin), pas l'AWS de fb. Le code reste agnostique à l'hébergeur ; le choix se matérialise à M4.
- **Distribution = broadcast sur un canal Telegram unique.** Le bot suit les 93 marchés et publie chaque changement dans un seul canal ; les abonnés voient tout. Pas de sélection ni de commandes par utilisateur (conforme au SPEC, outil public/retail). Filtrage par utilisateur = extension future éventuelle (M6).
- **Périmètre = dex `xyz` uniquement**, filtré par `dex="xyz"` dans l'API (pas par adresse deployer).
- **Surveillance par diff d'état** (agnostique à l'adresse-auteur) → capte aussi les changements signés par les sub-deployers.

---

## 3. Découvertes techniques (données réelles, M1)

- **`marginMode` n'est présent dans l'API que pour les marchés isolés** (`strictIsolated`/`noCross`, avec `onlyIsolated:true`). Pour un marché en cross (`normal`), le champ **disparaît**. → on normalise `absent → "normal"` pour que le diff capte bien le passage en cross (l'event clé selon fb). Verrouillé par un test.
- **Total OI cap du dex** observé : `7 000 000 000` ; **93 marchés** dont plusieurs delistés (`isDelisted:true`).

---

## 4. Points à confirmer avec fb (to-do débrief)

- [ ] **Halts / reprises : on ne sait pas encore les détecter.** Aucun champ de halt dans `meta` ni `metaAndAssetCtxs` ; seul `isDelisted` existe (delisting permanent ≠ halt temporaire). Hypothèse : `isHalted` n'apparaît que quand un marché est halté. → fb confirme-t-il le mécanisme, ou on attend d'observer un vrai halt ? **(seul vrai inconnu côté données)**
- [ ] **Postgres** : qui la fournit / l'héberge (Hostinger avec le reste, ou autre) ?
- [x] **Canal Telegram cible** : canal de broadcast « XYZ Deployer Alerts » créé (privé pour l'instant, passable en public en 1 clic). Bot @tradexyz_alerts_bot admin. À confirmer avec fb : est-ce LE canal final, ou faut-il pointer ailleurs (canal public communautaire, etc.) ?
- [ ] **Un message par event, ou groupé** quand une action touche plusieurs coins ? (actuellement : un message par event).
- [ ] **Latence visée** + **rate limits** connus de l'info API (pour calibrer l'intervalle de poll, cible 2–5 s).
- [ ] **Cross en live** : un marché peut-il réellement passer en `normal` (cross) après listing, ou est-ce figé ? (on saura le détecter de toute façon via le diff, mais bon à savoir).

---

## 5. Journal

- **2026-06-21** — M1 terminé : env + lecture API réelle (93 coins) + normalisation `marginMode` + 8 tests verts. Décisions Hostinger & broadcast actées. Limite halts identifiée et consignée.
- **2026-06-21** — M2 (diff) : moteur de diff `src/events.py` (events typés + `dedup_key`), seed silencieux au 1er run, boucle daemon en mémoire. 12 tests de diff verts (20 au total), validé en live. Persistance Postgres = prochaine étape.
- **2026-06-21** — M2 (persistance) : `src/db.py` (asyncpg) — load/save snapshot + insertion idempotente des events. `run_loop` charge la baseline depuis Postgres. 5 tests d'intégration (25 au total). Validé en live : RUN 1 = seed (93 coins), RUN 2 = pas de seed (baseline rechargée). **M2 terminé.** Prochaine étape : M3 (Telegram).
- **2026-06-21** — M3 (dry-run) : `src/messages.py` (templates) + `src/telegram.py` (envoi + dry-run) + câblage `run_loop` (envoi puis `mark_notified`). 13 tests (38 au total). Démo live dry-run OK (messages formatés conformes SPEC §7). Reste : token BotFather + chat_id pour l'envoi réel. Prochaine étape : M4 (daemon/systemd/déploiement Hostinger).
- **2026-06-21** — M3 **terminé** : bot `@tradexyz_alerts_bot` créé, token + chat_id configurés (`.env` local non commité), envoi réel validé (2 messages reçus). Cible actuelle = chat privé de test ; à terme pointer sur le canal de broadcast. Prochaine étape : M4.
- **2026-06-21** — Canal de broadcast « XYZ Deployer Alerts » créé + bot admin, envoi validé. Messages publics passés en **anglais** (audience internationale). 38 tests.
- **2026-06-21** — M4 (code) : `run_loop` durci (backoff exponentiel plafonné, heartbeat, arrêt propre SIGTERM), `run_cycle` factorisé + testé, unit systemd (`deploy/xyz-bot.service`) + runbook (`deploy/DEPLOY.md`). 43 tests verts, arrêt propre SIGTERM validé en live. Reste : déployer sur la VM Hostinger (Ubuntu, en provisioning).
- **2026-06-21** — M4 **déployé en prod** : VPS Hostinger Ubuntu 24.04 (`217.65.145.163`), Postgres 16 locale, service systemd `xyz-bot` actif + enabled (boot), envoi réel Telegram. **Le bot tourne 24/7.** Persistance validée sur le VPS (pas de re-seed au restart). M1→M4 terminés.
- **2026-06-21** — Durcissement SSH (auth par clé uniquement) + doc d'exploitation `deploy/OPS.md`. **Page de statut publique** ajoutée : service web séparé (`src/web.py`, aiohttp), heartbeat en base, systemd `xyz-bot-web`, en ligne sur http://217.65.145.163:8080/ (+ `/status.json`). 50 tests verts. À voir avec fb : domaine + HTTPS pour la page si on l'ouvre largement.
