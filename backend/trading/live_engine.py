"""
Live Options Trading Engine — buy-side index options via Kite Connect.
"""

from datetime import datetime

from backend.database import supabase_db as db
from backend.core.kite_client import kite_client
from backend.risk import risk_manager as rm
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)

MODE = "live"


def open_position(signal: dict) -> dict | None:
    """Place a live NFO options BUY order via Kite Connect."""
    if signal.get("signal") == "SKIP" or not signal.get("tradingsymbol"):
        return None

    tradingsymbol = signal["tradingsymbol"]
    lots          = signal.get("lots", 1)
    lot_size      = signal.get("lot_size", settings.nifty_lot_size)
    qty           = lots * lot_size

    try:
        order_id = kite_client.place_order(
            tradingsymbol=tradingsymbol,
            exchange="NFO",
            transaction_type=kite_client.TRANSACTION_BUY,
            quantity=qty,
            order_type="MARKET",
            product="NRML",
        )
        logger.info(f"[LIVE] Order placed: BUY {qty}x{tradingsymbol} | order_id={order_id}")
    except Exception as e:
        logger.error(f"[LIVE] Order placement failed for {tradingsymbol}: {e}")
        return None

    entry_premium = signal.get("entry_premium", 0)
    stop_prem     = round(entry_premium * (1 - settings.option_stop_loss_pct / 100), 2)
    target_prem   = round(entry_premium * settings.option_target_multiplier, 2)

    trade = db.create_trade({
        "symbol":        tradingsymbol,
        "mode":          MODE,
        "side":          "BUY",
        "entry_price":   entry_premium,
        "quantity":      qty,
        "stop_loss":     stop_prem,
        "target":        target_prem,
        "exchange":      "NFO",
        "product":       "NRML",
        "status":        "open",
        "kite_order_id": str(order_id),
        "notes": (
            f"lots={lots} lot_size={lot_size} index={signal.get('index')} "
            f"strike={signal.get('strike')} type={signal.get('option_type')} "
            f"expiry={signal.get('expiry')}"
        ),
    })

    db.create_position({
        "symbol":        tradingsymbol,
        "mode":          MODE,
        "side":          "BUY",
        "entry_price":   entry_premium,
        "current_price": entry_premium,
        "quantity":      qty,
        "stop_loss":     stop_prem,
        "target":        target_prem,
        "exchange":      "NFO",
        "product":       "NRML",
        "trade_id":      trade.get("id"),
        "unrealized_pnl": 0.0,
    })

    open_positions = db.get_positions(mode=MODE)
    rm.update_position_count(len(open_positions))
    return trade


def close_position(position: dict, reason: str = "signal") -> float:
    """Close a live NFO options position via Kite."""
    symbol = position["symbol"]

    try:
        kite_client.place_order(
            tradingsymbol=symbol,
            exchange="NFO",
            transaction_type=kite_client.TRANSACTION_SELL,
            quantity=position["quantity"],
            order_type="MARKET",
            product="NRML",
        )
    except Exception as e:
        logger.error(f"[LIVE] Close order failed for {symbol}: {e}")
        return 0.0

    exit_price = position.get("current_price") or position["entry_price"]
    pnl = round((exit_price - position["entry_price"]) * position["quantity"], 2)

    if position.get("trade_id"):
        db.update_trade(position["trade_id"], {
            "exit_price": exit_price,
            "exit_time":  datetime.utcnow().isoformat(),
            "pnl":        pnl,
            "status":     "closed",
        })

    db.delete_position(position["id"])
    open_positions = db.get_positions(mode=MODE)
    rm.update_position_count(len(open_positions))

    logger.info(f"[LIVE] Closed {symbol} @ ₹{exit_price:.1f} P&L: ₹{pnl:+.0f} | {reason}")
    return pnl


def sync_live_positions() -> None:
    """Sync Kite positions with local DB (update prices)."""
    try:
        kite_pos   = kite_client.get_positions()
        day_pos    = kite_pos.get("day", [])
        positions  = db.get_positions(mode=MODE)
        kite_map   = {p["tradingsymbol"]: p for p in day_pos}

        for pos in positions:
            kp = kite_map.get(pos["symbol"])
            if kp:
                curr = kp.get("last_price", pos.get("current_price", pos["entry_price"]))
                unrealized = round((curr - pos["entry_price"]) * pos["quantity"], 2)
                db.update_position(pos["id"], {"current_price": curr, "unrealized_pnl": unrealized})
    except Exception as e:
        logger.error(f"[LIVE] Position sync failed: {e}")


def squareoff_all() -> float:
    """EOD square-off all live options positions."""
    positions = db.get_positions(mode=MODE)
    total_pnl = sum(close_position(pos, reason="eod_squareoff") for pos in positions)
    logger.info(f"[LIVE] EOD square-off complete. Net P&L: ₹{total_pnl:+.2f}")
    return total_pnl
