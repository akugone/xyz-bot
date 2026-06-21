-- Schéma PostgreSQL du bot xyz-bot
-- Voir CLAUDE.md / ../xyz-deployer-bot-SPEC.md §6

-- État courant par (dex, coin) : base du diff
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

-- Limites globales du dex
CREATE TABLE IF NOT EXISTS dex_state (
  dex          TEXT PRIMARY KEY,
  total_oi_cap NUMERIC,
  updated_at   TIMESTAMPTZ DEFAULT now()
);

-- Heartbeat / santé du bot (1 ligne par dex) : alimente la page de statut publique
CREATE TABLE IF NOT EXISTS bot_status (
  dex                TEXT PRIMARY KEY,
  started_at         TIMESTAMPTZ,    -- début du process courant
  last_cycle_at      TIMESTAMPTZ,    -- dernier cycle (sert au up/down par fraîcheur)
  markets_count      INT,
  consecutive_errors INT DEFAULT 0
);

-- Journal des events détectés = idempotence anti-doublon
CREATE TABLE IF NOT EXISTS events (
  id          BIGSERIAL PRIMARY KEY,
  dex         TEXT NOT NULL,
  coin        TEXT,
  event_type  TEXT NOT NULL,     -- oi_cap_change | margin_mode_change | leverage_change | new_market | halt | ...
  old_value   TEXT,
  new_value   TEXT,
  dedup_key   TEXT UNIQUE,       -- ex: sha256(dex|coin|event_type|new_value) ; INSERT ON CONFLICT DO NOTHING
  notified_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ DEFAULT now()
);
