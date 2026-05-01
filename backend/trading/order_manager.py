from backend.config import settings
from backend.risk.risk_manager import validate_signal
from backend.trading import paper_engine, live_engine
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def process_signal(signal: dict) -> dict:
    """
    Validate signal → execute via paper or live engine.
    Signal must include: tradingsymbol, signal (BUY_CE/BUY_PE/SKIP),
    lots, lot_size, entry_premium.
    """
    sig_type = signal.get("signal", "SKIP")

    if sig_type == "SKIP":
        return {"executed": False, "reason": "SKIP signal"}

    approved, reason = validate_signal(signal)
    if not approved:
        logger.info(f"Signal rejected: {reason}")
        return {"executed": False, "reason": reason}

    engine = paper_engine if settings.trading_mode == "paper" else live_engine
    trade = engine.open_position(signal)

    if trade:
        return {
            "executed":      True,
            "tradingsymbol": signal.get("tradingsymbol"),
            "side":          sig_type,
            "lots":          signal.get("lots"),
            "entry":         signal.get("entry_premium"),
            "stop_loss":     signal.get("stop_premium"),
            "target":        signal.get("target_premium"),
            "trade_id":      trade.get("id"),
            "mode":          settings.trading_mode,
        }

    return {"executed": False, "reason": "Engine returned None"}
