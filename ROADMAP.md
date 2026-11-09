# Roadmap — xyz deployer bot

> Living roadmap, updated as we go. See also `HANDOVER.md` (status & open questions),
> `xyz-deployer-bot-SPEC.md` (spec), `xyz-bot/deploy/OPS.md` (operations).
> Last updated: **2026-06-22**.

---

## ✅ Done

- **M1 — Read**: Hyperliquid info API client + per-coin snapshot (93 markets).
- **M2 — Diff + persistence**: diff engine (typed events, dedup), Postgres (silent seed, survives restart).
- **M3 — Notifications**: Telegram sending to the broadcast channel "XYZ Deployer Alerts" (messages in **English**).
- **M4 — Deployment**: hardened daemon (backoff, heartbeat, graceful shutdown) in production on a Hostinger VPS, systemd, 24/7.
- **Public status page**: http://<VPS_IP>:8080/ (read-only DB role, cache, hardened units).
  Enriched: tracked-tokens tooltip, OI-cap amounts formatted, "Last check" as absolute UTC time,
  "Running since" (uptime), header links (Telegram + Uptime).
- **External uptime monitoring**: BetterStack pings `/status.json`, public uptime page
  (https://xyzbot.betteruptime.com/) with % + history, **and alerts if the VPS itself goes down** —
  closes the "who watches the watcher" blind spot (the bot can't alert when it's the one that's down).
- **Code review & security**: helper dedup, dead code removed, least privilege, SSH/systemd hardening.
- **M5 (partial)**: rate limits verified (see below); **API down/recovered** alert to the admin chat; `growth_mode_change` + `relisted` events added; end-to-end validated on a real change (controlled test).

---

## 🔜 Short term (next steps)

- [x] **Test on a real config change** → validated end-to-end in production via a controlled baseline test (real `oi_cap_change` + `growth_mode_change` alerts fired, then self-healed).
- [ ] **Confirm the halt mechanism** with the trade.xyz team (API field not observed — see `HANDOVER.md`).
- [ ] **Disambiguate "fresh (re)listing with no volume" from a real halt** — observed on `xyz:STRC` (2026-06-23): market present in the universe, oracle/mark ticking and order book quoted, but `openInterest: 0.0` and `dayNtlVlm: 0.0` → the trade.xyz UI shows "No data here" (no candles, empty trade history). There is no explicit halt flag in the API, so a halt and a just-relisted market currently look similar (both have no activity). Decide how the bot should classify this (e.g. relisted-but-idle vs halted) so we don't false-positive on relistings. Tied to the halt-mechanism confirmation above.
- [ ] **Confirm latency expectations** with the trade.xyz team: is the target retail (2–5s, current design), or is sub-second needed (MM-grade)? See the constraint below — sub-second is a different architecture, not a tuning.
- [x] **Open the channel to the public** — done; "XYZ Deployer Alerts" is now a public channel.

## 🌍 Medium term

- [ ] **Domain + HTTPS** for the status page (Caddy, auto-TLS) → clean URL `https://status.<domain>`.
- [~] **Enrich the page**: ✅ Telegram link + tracked-tokens tooltip done. Remaining: markets sitting
  at their OI cap. (Uptime history is now provided externally by BetterStack.)
- [ ] **Backups**: the DB is reconstructible (re-seed), but a daily `events` dump (audit trail) would be a plus.

## 🧪 Long term / options (M6)

- [ ] **Pre-OI-increase signal**: reintroduce `perpsAtOpenInterestCap` / `metaAndAssetCtxs` (real OI vs cap).
- [ ] **Multi-dex**: generalize beyond `xyz` (the code already filters by `dex`).
- [ ] **Funding multiplier**: populate `funding_mult` (via `perpDexs.assetToFundingMultiplier`) if useful.
- [ ] **Second channel / verbosity**: MM vs public channel, or filtering by event type.

---

## 📊 Reference — Hyperliquid API rate limits (verified 2026-06-21)

- Aggregated limit: **1200 weight / minute / IP** (across all REST requests).
- `meta` and `perpDexLimits` = **20 weight each** (default for `info` requests).
- **Our usage**: 2 requests/cycle = 40/cycle.
  - poll **5s** → 12 cycles/min → **480/min (~40%)** ✅ comfortable margin (current setting).
  - poll **3s** → 20 cycles/min → 800/min (~67%) ✅ still fine for more reactivity.
  - poll **2s** → 30 cycles/min → 1200/min (**100% = do not**).
- **Conclusion**: 5s is safe; **do not go below ~3s**. Rate limiting is not a concern at the current setting.
- Source: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits

### Latency floor & the sub-second case (architectural constraint)

- On the **public API**, the latency floor is **~3–5s** (driven by the 1200 weight/min cap, not by our code).
  A **sub-second** target (e.g. 1 call/s over 2–3 endpoints = 2400–3600 weight/min) **exceeds the public
  rate limit** — it is not reachable by tuning the poll interval.
- This is **out of scope** for the current project: the audience is **retail / community** (2–5s is fine);
  market makers, who would need sub-second, were **explicitly excluded** during scoping.
- **If** sub-second is ever required, it means a **different architecture**, not a config change:
  - **Private Hyperliquid node** → read L1 actions directly, ~100ms (heavy infra, different detection model).
  - **gRPC streaming via a provider** (Quicknode, Dwellir…) → sub-second, with infra cost.
  - **Public API only** → ~3–5s floor, no better.
  (The WebSocket API does not help: no WS feed exists for these deployer config changes.)
- → Confirm the latency expectation with the trade.xyz team before considering any of this.
