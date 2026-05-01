"""
ARC Trading Bot — Supabase Migration Runner
============================================
Creates all tables in Supabase without needing a direct TCP connection.
Uses the Supabase Management API (HTTPS).

Usage:
    python migrate.py --token YOUR_PERSONAL_ACCESS_TOKEN

Get token from: https://supabase.com/dashboard/account/tokens
  → "Generate new token" → copy it → paste below or pass as --token
"""

import argparse
import sys
import requests

# ── Config ─────────────────────────────────────────────────────────────────

PROJECT_REF = "yebwnkmlznpeizydbnvc"   # from your Supabase URL

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id            SERIAL PRIMARY KEY,
    symbol        VARCHAR(50)  NOT NULL,
    mode          VARCHAR(10)  NOT NULL DEFAULT 'paper',
    side          VARCHAR(4)   NOT NULL,
    entry_price   FLOAT        NOT NULL,
    exit_price    FLOAT,
    quantity      INTEGER      NOT NULL,
    pnl           FLOAT,
    entry_time    TIMESTAMP    DEFAULT NOW(),
    exit_time     TIMESTAMP,
    signal_id     INTEGER,
    status        VARCHAR(20)  DEFAULT 'open',
    stop_loss     FLOAT,
    target        FLOAT,
    exchange      VARCHAR(10)  DEFAULT 'NFO',
    product       VARCHAR(10)  DEFAULT 'NRML',
    kite_order_id VARCHAR(50),
    notes         TEXT
);
CREATE INDEX IF NOT EXISTS ix_trades_symbol ON trades (symbol);
CREATE INDEX IF NOT EXISTS ix_trades_status ON trades (status);

CREATE TABLE IF NOT EXISTS positions (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(50)  NOT NULL,
    mode            VARCHAR(10)  NOT NULL DEFAULT 'paper',
    side            VARCHAR(4)   NOT NULL,
    entry_price     FLOAT        NOT NULL,
    current_price   FLOAT,
    quantity        INTEGER      NOT NULL,
    unrealized_pnl  FLOAT        DEFAULT 0.0,
    stop_loss       FLOAT,
    target          FLOAT,
    opened_at       TIMESTAMP    DEFAULT NOW(),
    trade_id        INTEGER      REFERENCES trades(id),
    exchange        VARCHAR(10)  DEFAULT 'NFO',
    product         VARCHAR(10)  DEFAULT 'NRML'
);
CREATE INDEX IF NOT EXISTS ix_positions_symbol ON positions (symbol);
CREATE INDEX IF NOT EXISTS ix_positions_mode   ON positions (mode);

CREATE TABLE IF NOT EXISTS signals (
    id                   SERIAL PRIMARY KEY,
    symbol               VARCHAR(50)  NOT NULL,
    index_name           VARCHAR(20),
    signal               VARCHAR(10)  NOT NULL,
    option_type          VARCHAR(2),
    strike               FLOAT,
    expiry               VARCHAR(20),
    lots                 INTEGER,
    lot_size             INTEGER,
    confidence           FLOAT        DEFAULT 5.0,
    entry                FLOAT,
    target               FLOAT,
    stop_loss            FLOAT,
    max_loss             FLOAT,
    reasoning            TEXT,
    indicators_json      JSONB,
    market_context_json  JSONB,
    executed             BOOLEAN      DEFAULT FALSE,
    created_at           TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_signals_symbol     ON signals (symbol);
CREATE INDEX IF NOT EXISTS ix_signals_created_at ON signals (created_at DESC);

CREATE TABLE IF NOT EXISTS day_classifications (
    id                   SERIAL PRIMARY KEY,
    date                 DATE         UNIQUE NOT NULL,
    score                FLOAT        NOT NULL,
    buy_side_score       FLOAT,
    classification       VARCHAR(10)  NOT NULL,
    vix                  FLOAT,
    iv_rank              FLOAT,
    premium_environment  VARCHAR(20),
    fii_net              FLOAT,
    fii_fut_ls_ratio     FLOAT,
    dii_net              FLOAT,
    pcr                  FLOAT,
    nifty_gap            FLOAT,
    global_sentiment     VARCHAR(30),
    ml_direction         VARCHAR(20),
    ml_regime            VARCHAR(20),
    reasons_json         JSONB,
    market_context_json  JSONB,
    created_at           TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_day_classifications_date ON day_classifications (date DESC);

CREATE TABLE IF NOT EXISTS pnl_snapshots (
    id              SERIAL PRIMARY KEY,
    date            DATE         NOT NULL,
    mode            VARCHAR(10)  DEFAULT 'paper',
    realized_pnl    FLOAT        DEFAULT 0.0,
    unrealized_pnl  FLOAT        DEFAULT 0.0,
    total_trades    INTEGER      DEFAULT 0,
    winning_trades  INTEGER      DEFAULT 0,
    losing_trades   INTEGER      DEFAULT 0,
    win_rate        FLOAT        DEFAULT 0.0,
    portfolio_value FLOAT        NOT NULL,
    created_at      TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_pnl_snapshots_date ON pnl_snapshots (date DESC);

CREATE TABLE IF NOT EXISTS bot_config (
    id         SERIAL PRIMARY KEY,
    key        VARCHAR(100) UNIQUE NOT NULL,
    value      TEXT         NOT NULL,
    updated_at TIMESTAMP    DEFAULT NOW()
);
"""


def run_migration(token: str):
    url = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    print(f"Running schema against project {PROJECT_REF}...\n")

    resp = requests.post(url, headers=headers, json={"query": SCHEMA_SQL}, timeout=30)

    if resp.status_code in (200, 201):
        print("All tables created successfully!")
    else:
        body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else resp.text
        print(f"Migration failed (HTTP {resp.status_code}): {body}")
        sys.exit(1)
        print("\nStart the bot:")
        print("  venv/bin/uvicorn backend.main:app --reload")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create Supabase tables via Management API")
    parser.add_argument(
        "--token", "-t",
        required=True,
        help=(
            "Supabase personal access token. "
            "Get it from: https://supabase.com/dashboard/account/tokens"
        ),
    )
    args = parser.parse_args()
    run_migration(args.token)
