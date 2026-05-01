from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, DateTime, Boolean, Text, Date, JSON
)
from backend.database.db import Base


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    mode = Column(String(10), nullable=False, default="paper")  # paper | live
    side = Column(String(4), nullable=False)                    # BUY | SELL
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=False)
    pnl = Column(Float, nullable=True)
    entry_time = Column(DateTime, default=datetime.utcnow)
    exit_time = Column(DateTime, nullable=True)
    signal_id = Column(Integer, nullable=True)
    status = Column(String(20), default="open")                 # open | closed | cancelled
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    exchange = Column(String(10), default="NSE")
    product = Column(String(10), default="MIS")
    kite_order_id = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False, index=True)
    mode = Column(String(10), nullable=False, default="paper")
    side = Column(String(4), nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=False)
    unrealized_pnl = Column(Float, default=0.0)
    stop_loss = Column(Float, nullable=True)
    target = Column(Float, nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow)
    trade_id = Column(Integer, nullable=True)
    exchange = Column(String(10), default="NSE")
    product = Column(String(10), default="MIS")


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(50), nullable=False, index=True)     # e.g. NIFTY25MAY24000CE
    index = Column(String(20), nullable=True)                   # NIFTY | BANKNIFTY
    signal = Column(String(10), nullable=False)                 # BUY_CE | BUY_PE | SKIP
    option_type = Column(String(2), nullable=True)              # CE | PE
    strike = Column(Float, nullable=True)
    expiry = Column(String(20), nullable=True)
    lots = Column(Integer, nullable=True)
    lot_size = Column(Integer, nullable=True)
    confidence = Column(Float, default=5.0)
    entry = Column(Float, nullable=True)                        # entry premium
    target = Column(Float, nullable=True)                       # target premium
    stop_loss = Column(Float, nullable=True)                    # stop premium
    max_loss = Column(Float, nullable=True)
    reasoning = Column(Text, nullable=True)
    indicators_json = Column(JSON, nullable=True)
    market_context_json = Column(JSON, nullable=True)
    executed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class DayClassification(Base):
    __tablename__ = "day_classifications"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, index=True)
    score = Column(Float, nullable=False)                       # 1-10
    buy_side_score = Column(Float, nullable=True)               # 0-10 buy-side conditions
    classification = Column(String(10), nullable=False)         # GOOD | NEUTRAL | BAD
    vix = Column(Float, nullable=True)
    iv_rank = Column(Float, nullable=True)
    premium_environment = Column(String(20), nullable=True)     # CHEAP | FAIR | EXPENSIVE
    fii_net = Column(Float, nullable=True)
    fii_fut_ls_ratio = Column(Float, nullable=True)
    dii_net = Column(Float, nullable=True)
    pcr = Column(Float, nullable=True)
    nifty_gap = Column(Float, nullable=True)
    global_sentiment = Column(String(30), nullable=True)
    ml_direction = Column(String(20), nullable=True)
    ml_regime = Column(String(20), nullable=True)
    reasons_json = Column(JSON, nullable=True)
    market_context_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PnlSnapshot(Base):
    __tablename__ = "pnl_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, index=True)
    mode = Column(String(10), default="paper")
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    portfolio_value = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class BotConfig(Base):
    __tablename__ = "bot_config"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
