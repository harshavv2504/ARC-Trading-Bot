"""
Options Paper Trading Engine — buy-side only.

Tracks option positions by premium (not underlying price).
P&L = (current_premium - entry_premium) × lots × lot_size

Stop loss: triggered when premium drops to stop_premium (default 50% of entry).
Target:    triggered when premium reaches target_premium (default 2x entry).
EOD:       all positions closed at market premium at 15:20.
"""

from datetime import datetime

from backend.database import supabase_db as db
from backend.risk import risk_manager as rm
from backend.core.market_data import get_option_ltp
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)

MODE = "paper"


def open_position(signal: dict) -> dict | None:
    """
    Open a paper options position.
    Signal must contain: index, tradingsymbol, option_type, strike,
                         lots, lot_size, entry_premium.
    """
    if signal.get("signal") == "SKIP" or not signal.get("tradingsymbol"):
        return None

    tradingsymbol = signal["tradingsymbol"]
    lots          = signal.get("lots", 1)
    lot_size      = signal.get("lot_size", settings.nifty_lot_size)
    qty           = lots * lot_size

    live_premium = get_option_ltp(tradingsymbol)
    entry_premium = live_premium or signal.get("entry_premium", 0)
    if not entry_premium:
        logger.warning(f"Paper: cannot get entry premium for {tradingsymbol}")
        return None

    stop_prem   = round(entry_premium * (1 - settings.option_stop_loss_pct / 100), 2)
    target_prem = round(entry_premium * settings.option_target_multiplier, 2)
    max_loss    = round((entry_premium - stop_prem) * qty, 2)

    capital_needed = entry_premium * qty
    if capital_needed > settings.portfolio_value * settings.max_premium_pct / 100:
        logger.warning(
            f"Paper: {tradingsymbol} requires ₹{capital_needed:.0f} "
            f"(> {settings.max_premium_pct}% of portfolio). Skipping."
        )
        return None

    trade = db.create_trade({
        "symbol": tradingsymbol,
        "mode": MODE,
        "side": "BUY",
        "entry_price": entry_premium,
        "quantity": qty,
        "stop_loss": stop_prem,
        "target": target_prem,
        "exchange": "NFO",
        "product": "NRML",
        "status": "open",
        "notes": (
            f"lots={lots} lot_size={lot_size} index={signal.get('index')} "
            f"strike={signal.get('strike')} type={signal.get('option_type')} "
            f"expiry={signal.get('expiry')}"
        ),
    })

    db.create_position({
        "symbol": tradingsymbol,
        "mode": MODE,
        "side": "BUY",
        "entry_price": entry_premium,
        "current_price": entry_premium,
        "quantity": qty,
        "stop_loss": stop_prem,
        "target": target_prem,
        "exchange": "NFO",
        "product": "NRML",
        "trade_id": trade.get("id"),
        "unrealized_pnl": 0.0,
    })

    open_positions = db.get_positions(mode=MODE)
    rm.update_position_count(len(open_positions))

    logger.info(
        f"[PAPER OPTIONS] BUY {lots}L × {tradingsymbol} @ ₹{entry_premium:.1f} "
        f"SL=₹{stop_prem:.1f} T=₹{target_prem:.1f} MaxLoss=₹{max_loss:.0f}"
    )
    return trade


def close_position(position: dict, reason: str = "signal", exit_premium: float | None = None) -> float:
    """Close a paper options position. Returns P&L in rupees."""
    if exit_premium is None:
        exit_premium = get_option_ltp(position["symbol"]) or position.get("current_price", position["entry_price"])

    pnl = round((exit_premium - position["entry_price"]) * position["quantity"], 2)

    if position.get("trade_id"):
        db.update_trade(position["trade_id"], {
            "exit_price": exit_premium,
            "exit_time": datetime.utcnow().isoformat(),
            "pnl": pnl,
            "status": "closed",
        })

    db.delete_position(position["id"])

    open_positions = db.get_positions(mode=MODE)
    rm.update_position_count(len(open_positions))

    prefix = "+" if pnl >= 0 else ""
    logger.info(
        f"[PAPER OPTIONS] CLOSE {position['symbol']} @ ₹{exit_premium:.1f} "
        f"P&L: {prefix}₹{pnl:.0f} | Reason: {reason}"
    )
    return pnl


def update_positions() -> dict:
    """Mark open options positions to market; trigger SL/target closes."""
    positions = db.get_positions(mode=MODE)
    positions = [p for p in positions if p.get("exchange") == "NFO"]

    if not positions:
        rm.update_daily_pnl(0.0, 0.0)
        return {"open": 0, "unrealized_pnl": 0.0}

    total_unrealized = 0.0
    closed_this_cycle: list[str] = []

    for pos in positions:
        live = get_option_ltp(pos["symbol"])
        if not live:
            continue

        unrealized = round((live - pos["entry_price"]) * pos["quantity"], 2)
        db.update_position(pos["id"], {"current_price": live, "unrealized_pnl": unrealized})
        total_unrealized += unrealized

        if pos.get("stop_loss") and live <= pos["stop_loss"]:
            close_position(pos, reason="stop_loss", exit_premium=live)
            closed_this_cycle.append(pos["symbol"])
            continue

        if pos.get("target") and live >= pos["target"]:
            close_position(pos, reason="target_hit", exit_premium=live)
            closed_this_cycle.append(pos["symbol"])
            continue

    closed_trades = db.get_trades(mode=MODE, status="closed", limit=500)
    realized = sum((t.get("pnl") or 0) for t in closed_trades)
    rm.update_daily_pnl(realized, total_unrealized)

    if closed_this_cycle:
        logger.info(f"[PAPER] Auto-closed: {closed_this_cycle}")

    return {
        "open": len(positions) - len(closed_this_cycle),
        "unrealized_pnl": round(total_unrealized, 2),
        "closed_this_cycle": closed_this_cycle,
    }


def squareoff_all() -> float:
    """EOD square-off: close all open options positions at market premium."""
    positions = db.get_positions(mode=MODE)
    positions = [p for p in positions if p.get("exchange") == "NFO"]

    total_pnl = 0.0
    for pos in positions:
        total_pnl += close_position(pos, reason="eod_squareoff")

    logger.info(f"[PAPER OPTIONS] EOD square-off: {len(positions)} positions | Net P&L: ₹{total_pnl:+.0f}")
    return total_pnl


def get_portfolio_value() -> float:
    positions = db.get_positions(mode=MODE)
    unrealized = sum(p.get("unrealized_pnl") or 0 for p in positions)
    closed_trades = db.get_trades(mode=MODE, status="closed", limit=500)
    realized = sum((t.get("pnl") or 0) for t in closed_trades)
    return rm.get_risk_state().portfolio_value + realized + unrealized


def get_open_positions_summary() -> list[dict]:
    positions = db.get_positions(mode=MODE)
    positions = [p for p in positions if p.get("exchange") == "NFO"]
    result = []
    for pos in positions:
        entry = pos["entry_price"]
        curr  = pos.get("current_price") or entry
        pct   = round((curr - entry) / entry * 100, 1) if entry else 0
        result.append({
            "id":             pos["id"],
            "symbol":         pos["symbol"],
            "quantity":       pos["quantity"],
            "entry_premium":  entry,
            "current_premium": curr,
            "change_pct":     pct,
            "unrealized_pnl": pos.get("unrealized_pnl") or 0,
            "stop_loss":      pos.get("stop_loss"),
            "target":         pos.get("target"),
            "stop_distance_pct":   round((curr - pos["stop_loss"]) / curr * 100, 1) if pos.get("stop_loss") else None,
            "target_distance_pct": round((pos["target"] - curr) / curr * 100, 1) if pos.get("target") else None,
        })
    return result
