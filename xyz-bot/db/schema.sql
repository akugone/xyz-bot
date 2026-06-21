-- PostgreSQL schema for xyz-bot
-- See CLAUDE.md / ../xyz-deployer-bot-SPEC.md §6

-- Current state per (dex, coin): the basis for the diff
CREATE TABLE IF NOT EXISTS market_state (
  dex             TEXT NOT NULL,
  coin            TEXT NOT NULL,
  max_leverage    INT,
  margin_mode     TEXT,          -- strictIsolated | noCross | normal
  margin_table_id INT,
  oi_cap          NUMERIC,       -- notional cap (coinToOiCap)
  is_listed       BOOLEAN DEFAULT TRUE,
  is_halted       BOOLEAN,
  funding_mult    NUMERIC,
  growth_mode     BOOLEAN,
  updated_at      TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (dex, coin)
);

-- Dex-wide limits
CREATE TABLE IF NOT EXISTS dex_state (
  dex          TEXT PRIMARY KEY,
  total_oi_cap NUMERIC,
  updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Bot heartbeat / health (1 row per dex): feeds the public status page
CREATE TABLE IF NOT EXISTS bot_status (
  dex                TEXT PRIMARY KEY,
  started_at         TIMESTAMPTZ,    -- start of the current process
  last_cycle_at      TIMESTAMPTZ,    -- last cycle (drives up/down by freshness)
  markets_count      INT,
  consecutive_errors INT DEFAULT 0
);

-- Journal of detected events = anti-duplicate idempotency
CREATE TABLE IF NOT EXISTS events (
  id          BIGSERIAL PRIMARY KEY,
  dex         TEXT NOT NULL,
  coin        TEXT,
  event_type  TEXT NOT NULL,     -- oi_cap_change | margin_mode_change | leverage_change | new_market | growth_mode_change | halt | ...
  old_value   TEXT,
  new_value   TEXT,
  dedup_key   TEXT UNIQUE,       -- e.g. sha256(dex|coin|event_type|new_value) ; INSERT ON CONFLICT DO NOTHING
  notified_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT now()
);
