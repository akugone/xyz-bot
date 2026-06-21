# Concepts & terminology — Hyperliquid, HIP-3, trade.xyz, perps

> Reference notes on the domain concepts behind the bot (HIP-3, the deployer, margin, OI caps,
> liquidation/backstop risk). Complements the build plan in `../xyz-deployer-bot-SPEC.md` — here
> we explain the *concepts*, not the project.

---

## 1. HIP-3 — the framework that opens markets

**HIP-3** = "Hyperliquid Improvement Proposal #3", activated on mainnet in October 2025.

HIP-3 is not a market — it is the *system* that lets any team deploy its own perp DEX on
Hyperliquid. Previously Hyperliquid alone decided which markets existed (BTC, ETH…). With HIP-3,
external "builders" deploy and operate their own markets.

Three pieces:
- **The builder**: the team launching its markets (e.g. trade.xyz).
- **The stake**: the right to deploy requires locking a large bond in **HYPE** (500,000 HYPE on
  mainnet). Anti-spam filter + commitment.
- **The responsibilities**: the builder then operates its market (oracle, liquidity, leverage, OI
  caps, settlement). Hyperliquid provides the infra (HyperCore, the L1 layer handling order books
  and on-chain settlement).

A **"dex"** = an instance deployed by a builder. `xyz` (trade.xyz) is one — the largest (~90% of
HIP-3 Open Interest, on tokenized equities/indices/commodities). Other builders have their own but
are small.

---

## 2. The deployer and its actions

**The deployer** = the **on-chain address** Hyperliquid granted the right to operate a dex. For
`xyz` it is `0x88806a71D74ad0a510b350545C9aE490912F0888` (+ a distinct "oracle updater" address for
prices).

Key point: **it is NOT a smart contract with an ABI.** The deployer signs **L1 actions**
(`PerpDeployAction`) processed by HyperCore. Analogy: **deployer = admin account, actions = admin
commands.**

The actions that change a market's config (the most useful to monitor):
- `registerAsset` — list a new asset
- `setOpenInterestCaps` — change the OI cap
- `setMarginModes` — change margin mode (strictIsolated ↔ noCross)
- `setMarginTableIds` — change the margin table (hence leverage)
- `haltTrading` — halt / resume a market
- `setFundingMultipliers`, `setFundingInterestRates` — tune funding
- `setOracle` — push the price (~every 3s; noise, not an "event")

Since these actions can't be read via an ABI, we **monitor the deployed state via the API and
diff** between two snapshots. (Technical detail in the spec.)

---

## 3. A market's parameters

### Open Interest (OI) & OI cap
- **OI** = total size of all open positions on a market — "how much money is committed".
- **OI cap** = the **maximum OI** the platform allows on that market.
- When the cap is reached: you can no longer **open** a position that would *increase* OI (you can
  still close). It's not a "stock" shortage — a perp is synthetic; it's a **risk ceiling** set by
  the deployer.

### Margin mode — *how collateral is shared*
- **Isolated**: margin is confined to the position. A liquidation only costs the allocated margin.
  - `strictIsolated`: isolated **and** margin not withdrawable from an open position.
  - `noCross`: isolated only.
- **Cross** (`normal`): the whole account balance is shared collateral. Capital-efficient, but a bad
  position can wipe everything (internal cascade).
- On a new/volatile market the deployer stays **conservative** (isolated, low leverage), then loosens
  as the market matures.
- **Transition direction (confirmed)**: a market can only move toward **more flexibility**, in the
  order `strictIsolated → noCross → normal (cross)`. Never backwards.

### Leverage & margin tables
- **Leverage** = position/collateral multiplier (e.g. 10x).
- It's not a single number: a market points to a **margin table** (`marginTableId`) with **tiers**:
  the larger the position, the lower the max leverage. E.g. 0–1M$ → 10x, beyond → 5x. Risk guardrail.
  Bounded to 50x, ≤ 3 tiers.

### Funding & funding multiplier
- **Funding** = small periodic payment between longs and shorts to **keep the perp price pinned to
  the real price**. If too many longs (perp above real) → longs pay shorts, pulling the price back.
- **Funding multiplier** (0–10) = a per-market knob tuning the **strength** of that pull. On a
  "gappy" asset (tokenized equity traded 24/7 while the real equity closes nights/weekends), a high
  multiplier pulls the perp harder toward the real price.

---

## 4. Liquidation cascades, backstop & risk

Why config changes matter — and why market makers want to be warned about them.

- **Liquidation cascade**: a forced position close is a market order against the book. If it's large,
  it sweeps the best level, then the next, moving the price at each level. The higher the allowed OI,
  the larger the positions, the more violent the sweep — which can liquidate other traders too.
- **Backstop liquidator (HLP vault)**: an automatic protocol mechanism (Hyperliquid's **HLP** vault).
  It only steps in when the book is too thin to absorb a forced close, acting as **counterparty of
  last resort**. It then inherits the exposure and can go "into the red" if the price keeps moving the
  wrong way.
- **ADL (Auto-Deleveraging)**: when even the backstop / insurance fund isn't enough, the platform
  automatically reduces the opposite side's winning positions to balance the books. A last resort.
- **The market maker (MM)**: the actor that populates the book (continuous bids and asks around the
  price, earning the spread). During a sweep its bids get filled while the price collapses → it ends
  up long, at a loss. Hence the value of **warning** when a parameter changes (leverage, OI cap,
  margin) — the core rationale of the bot.

---

## 5. The OI cap cycle & the "snipe"

1. **Fill-up**: OI climbs toward the cap.
2. **Saturation**: the market reaches its cap → new entries are **blocked** = pent-up demand (not a
   queue: orders that would increase OI are simply rejected).
3. **Cap raised**: the deployer increases the ceiling (`setOpenInterestCaps`).
4. **Rush**: those waiting pile in. Since you can't pre-place an order, **bots fire at the millisecond**
   capacity frees up = the "snipe". The price moves with the pent-up demand (bullish in the MRVL case
   after the NVDA news → it pumps).

→ "A market sitting at its cap" is therefore a **leading signal** of an imminent OI increase. That
head-start is part of the bot's value.

---

## 6. Glossary

| Term | One line |
|---|---|
| **HIP-3** | Framework letting third parties deploy their own perp DEXs on Hyperliquid. |
| **Dex (xyz)** | A markets instance deployed by a builder; `xyz` = trade.xyz's. |
| **Deployer** | Admin address operating the dex by signing L1 actions (not a contract). |
| **Perp** | Synthetic futures contract with no expiry; you bet on price without owning the asset. |
| **Open Interest (OI)** | Total open positions on a market. |
| **OI cap** | Risk ceiling on OI set by the deployer; reached = no net opening. |
| **Funding** | Longs↔shorts payment that pins the perp price to the real one. |
| **Funding multiplier** | Per-market knob (0–10) tuning funding strength. |
| **Isolated / cross** | Margin confined per position / shared across the whole account. |
| **Leverage / margin table** | Position multiplier; defined in tiers (larger = less leverage). |
| **Liquidation cascade** | A large forced close sweeps several book levels → the price moves. |
| **Backstop liquidator (HLP)** | Automatic counterparty of last resort when the book can't absorb. |
| **ADL** | Forced reduction of winning positions when the backstop isn't enough. |
| **Market maker (MM)** | Posts bids+asks and earns the spread; wants warning when config changes. |
| **OI cap snipe** | Entering first (often via bots) as soon as a cap is raised. |
