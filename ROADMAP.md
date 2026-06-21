# Roadmap — xyz deployer bot

> Living roadmap, updated as we go. See also `HANDOVER.md` (status & open questions),
> `xyz-deployer-bot-SPEC.md` (spec), `xyz-bot/deploy/OPS.md` (operations).
> Last updated: **2026-06-21**.

---

## ✅ Done

- **M1 — Read**: Hyperliquid info API client + per-coin snapshot (93 markets).
- **M2 — Diff + persistence**: diff engine (typed events, dedup), Postgres (silent seed, survives restart).
- **M3 — Notifications**: Telegram sending to the broadcast channel "XYZ Deployer Alerts" (messages in **English**).
- **M4 — Deployment**: hardened daemon (backoff, heartbeat, graceful shutdown) in production on a Hostinger VPS, systemd, 24/7.
- **Public status page**: http://217.65.145.163:8080/ (read-only DB role, cache, hardened units).
- **Code review & security**: helper dedup, dead code removed, least privilege, SSH/systemd hardening.
- **M5 (partial)**: rate limits verified (see below); **API down/recovered** alert to the admin chat.

---

## 🔜 Short term (next steps)

- [ ] **Test on a real config change** of the dex (or simulated) → confirm the end-to-end flow in real conditions.
- [ ] **Confirm the halt mechanism** with the trade.xyz team (API field not observed — see `HANDOVER.md`).
- [ ] **Open the channel to the public** (switch the Telegram channel to public) once validated.

## 🌍 Medium term

- [ ] **Domain + HTTPS** for the status page (Caddy, auto-TLS) → clean URL `https://status.<domain>`.
- [ ] **Enrich the page**: channel subscribe link, markets sitting at their OI cap, mini history.
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
