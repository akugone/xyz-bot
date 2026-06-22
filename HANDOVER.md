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
| **M5 — Hardening** | ⏳ | rate limits verified, API-down alert done, end-to-end validated on a real change (controlled test). Remaining: confirm the halt mechanism |

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
- [ ] **Target latency**: is retail-grade (2–5s, current design) enough, or is sub-second needed? Sub-second
  is **not reachable on the public API** (the 1200 weight/min cap puts the floor at ~3–5s) — it would require
  a private node or gRPC streaming, i.e. a different architecture. MMs (who'd need it) were excluded during
  scoping, so the current design assumes retail. See `ROADMAP.md` → "Latency floor & the sub-second case".
- [ ] **Live cross transition**: can a market really switch to `normal` (cross) after listing, or is
  it fixed? (we detect it via the diff regardless, but good to know).
- [x] **Telegram channel**: the broadcast channel "XYZ Deployer Alerts" is now **public**. (Confirm
  with the trade.xyz team only if they want a different/community channel as the canonical one.)

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
  rate limits verified, API-down alert added. 72 tests green (~80% coverage; core logic ~100%,
  remaining gaps are the daemon-loop orchestration and web server bootstrap, validated live).
- **2026-06-21** — Added `growth_mode_change` event (🌱). End-to-end validated in production via a
  controlled test: tampered the stored baseline → the next cycle fired real `oi_cap_change` +
  `growth_mode_change` alerts to the channel, then self-healed (no duplicates).
- **2026-06-22** — Added `relisted` event (♻️). Spotted via ZHIPU: a previously delisted market that
  comes back flips `isDelisted` (False→listed) — it already exists in the universe so `new_market`
  doesn't fire. `relisted` now covers it (mirror of `delisted`). 72 tests green.
- **2026-06-22** — Broadcast channel "XYZ Deployer Alerts" switched to **public**. Docs de-duplicated
  (single source of truth per concern).
