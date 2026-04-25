-- Broker connections
CREATE TABLE IF NOT EXISTS broker_connections (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  provider text NOT NULL,
  credentials_encrypted text NOT NULL,
  last_sync_at timestamp,
  last_sync_status text DEFAULT 'pending',
  last_sync_error text,
  created_at timestamp DEFAULT now(),
  updated_at timestamp DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_broker_connections_user ON broker_connections(user_id);

-- Holdings
CREATE TABLE IF NOT EXISTS holdings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id text NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  symbol text NOT NULL,
  name text,
  currency text NOT NULL,
  instrument_type text NOT NULL,
  quantity numeric(28,8) NOT NULL,
  avg_cost numeric(28,8),
  as_of_date date,
  source text NOT NULL,
  last_price_error text,
  created_at timestamp DEFAULT now(),
  updated_at timestamp DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS holdings_account_symbol_type_uq ON holdings(account_id, symbol, instrument_type);
CREATE INDEX IF NOT EXISTS idx_holdings_account ON holdings(account_id);

-- Broker trades
CREATE TABLE IF NOT EXISTS broker_trades (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  symbol text NOT NULL,
  trade_date date NOT NULL,
  side text NOT NULL,
  quantity numeric(28,8) NOT NULL,
  price numeric(28,8) NOT NULL,
  currency text NOT NULL,
  external_id text NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS broker_trades_account_external_uq ON broker_trades(account_id, external_id);

-- Price snapshots
CREATE TABLE IF NOT EXISTS price_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  symbol text NOT NULL,
  currency text NOT NULL,
  date date NOT NULL,
  close numeric(28,8) NOT NULL,
  provider text NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS price_snapshots_symbol_date_uq ON price_snapshots(symbol, date);

-- Holding valuations
CREATE TABLE IF NOT EXISTS holding_valuations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  holding_id uuid NOT NULL REFERENCES holdings(id) ON DELETE CASCADE,
  date date NOT NULL,
  quantity numeric(28,8) NOT NULL,
  price numeric(28,8) NOT NULL,
  value_user_currency numeric(15,2) NOT NULL,
  is_stale boolean DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS holding_valuations_holding_date_uq ON holding_valuations(holding_id, date);
