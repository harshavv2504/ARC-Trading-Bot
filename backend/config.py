from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Kite Connect
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_access_token: str = ""

    # AI — use whichever key you have (OpenAI takes priority if both set)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    # Day classification: runs once/day — use smarter model
    ai_model_day: str = "gpt-5.4"
    # Signal generation: runs every 5 min — use fast/cheap model
    ai_model_signal: str = "gpt-5.4-mini"

    # Database
    database_url: str = "postgresql://postgres:password@localhost:5432/postgres"
    supabase_url: str = ""
    supabase_key: str = ""

    # Bot
    trading_mode: str = "paper"
    portfolio_value: float = 100000.0
    max_risk_per_trade: float = 2.0
    max_daily_drawdown: float = 6.0
    max_positions: int = 5
    min_rr_ratio: float = 2.0
    squareoff_time: str = "15:20"

    # Options trading (buy-side only)
    nifty_lot_size: int = 25
    banknifty_lot_size: int = 30
    max_iv_rank: float = 35.0          # skip buying when IV rank > this (expensive premium)
    min_dte: int = 4                   # skip options expiring within this many days
    option_stop_loss_pct: float = 50.0 # exit if premium drops 50% from entry
    option_target_multiplier: float = 2.0  # target = 2x entry premium
    max_premium_pct: float = 1.5       # max option premium as % of portfolio per trade
    index_universe: list = ["NIFTY", "BANKNIFTY"]  # which indices to trade

    # Server
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_port: int = 5173

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
