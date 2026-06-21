# Handover — xyz deployer alert bot (Hyperliquid HIP-3)

> Living document: project status, decisions, technical findings, and open questions.
> Full spec: `xyz-deployer-bot-SPEC.md`. Status page: `STATUS-PAGE.md`.
> Operations: `xyz-bot/deploy/OPS.md`. What's next: `ROADMAP.md`.
> Last updated: **2026-06-21**.

---

## 1. Status (by milestone)

| Milestone | State | Notes |
|---|---|---|
| M0 — Scoping | ✅ | events / audience / REST / sub-deployers settled with the trade.xyz team |
| **M1 — Read** | ✅ | info API client + per-coin snapshot (93 markets) |
| **M2 — Diff & persistence** | ✅ | diff engine + Postgres (asyncpg). Baseline survives restart (seed only on empty DB) |
| **M3 — Notifications** | ✅ | templates + Telegram, **live sending validated** to the broadcast channel "XYZ Deployer Alerts" (`@tradexyz_alerts_bot`, bot is admin). Public messages in **English** |
| **M4 — Daemon & deploy** | ✅ | **in production** on a Hostinger VPS (Ubuntu 24.04), systemd active + enabled at boot, local Postgres. Runs 24/7 |
| **Public status page** | ✅ | separate web service, read-only DB role, http://217.65.145.163:8080/ |
| **Code review & hardening** | ✅ | dedup of helpers, dead code removed, least privilege, SSH/systemd hardening |
| **M5 — Hardening** | ⏳ | rate limits verified, API-down alert done. Remaining: test on a real config change, confirm halt mechanism |

---

## 2. Decisions made

- **Hosting = Hostinger VPS**. The code is host-agnostic; the choice materialized at M4.
- **Distribution = broadcast to a single Telegram channel.** The bot watches all 93 markets and
  posts every change to one channel; subscribers see everything. No per-user selection or
  commands (matches the spec: public/retail tool). Per-user filtering = possible future extension.
- **Scope = `xyz` dex only**, filtered by `dex="xyz"` in the API (not by deployer address).
- **State-diff monitoring** (agnostic to the signing address) → also catches changes signed by
  sub-deployers.
- **Ops alerts** (API down/recovered) go to a private admin chat, not the public channel.

---

## 3. Technical findings (real data, M1)

- **`marginMode` is only present in the API for isolated markets** (`strictIsolated`/`noCross`,
  with `onlyIsolated:true`). For a cross market (`normal`), the field **disappears**. We normalize
  `absent → "normal"` so the diff correctly catches the move to cross. Locked by a test.
- **Observed dex total OI cap**: `7,000,000,000`; **93 markets**, several delisted (`isDelisted:true`).
- **Rate limits** (verified): aggregated 1200 weight/min/IP; `meta`+`perpDexLimits` = 40/cycle →
  ~40% at 5s polling. Safe floor ~3s. See `ROADMAP.md`.

---

## 4. Open questions (to confirm with the trade.xyz team)

- [ ] **Halts / resumes: not yet detectable.** No halt field in `meta` or `metaAndAssetCtxs`; only
  `isDelisted` exists (permanent delisting ≠ temporary halt). Hypothesis: `isHalted` only appears
  when a market is actually halted. → confirm the mechanism, or wait to observe a real halt.
  **(the only real unknown on the data side)**
- [ ] **One message per event, or grouped** when an action touches several coins? (currently: one
  message per event).
- [ ] **Target latency** + any known info-API rate limits beyond the documented 1200/min.
- [ ] **Live cross transition**: can a market really switch to `normal` (cross) after listing, or is
  it fixed? (we detect it via the diff regardless, but good to know).
- [ ] **Telegram channel**: is "XYZ Deployer Alerts" the final channel, or should it point elsewhere
  (community public channel, etc.)? Currently private, can be made public in one click.

---

## 5. Log

- **2026-06-21** — M1 done: env + live API read (93 markets) + `marginMode` normalization + tests.
- **2026-06-21** — M2 done: diff engine (`src/events.py`, typed events + `dedup_key`, silent seed) +
  Postgres persistence (`src/db.py`). Validated live: seed then no re-seed after restart.
- **2026-06-21** — M3 done: `src/messages.py` + `src/telegram.py`, wired into the loop. Bot
  `@tradexyz_alerts_bot` created, broadcast channel set up, live sending validated. Public messages
  switched to English (international audience).
- **2026-06-21** — M4 deployed to production: Hostinger VPS Ubuntu 24.04 (`217.65.145.163`), local
  Postgres 16, systemd `xyz-bot` active + enabled. Persistence validated on the VPS.
- **2026-06-21** — Public status page added (`src/web.py`, aiohttp, read-only DB role) + SSH/systemd
  hardening + ops docs.
- **2026-06-21** — Code review applied (cleanup, dead code removal, least privilege). M5 partial:
  rate limits verified, API-down alert added. 64 tests green (~80% coverage; core logic ~100%,
  remaining gaps are the daemon-loop orchestration and web server bootstrap, validated live).
