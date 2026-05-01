import math
from dataclasses import dataclass, field
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RiskState:
    portfolio_value: float = 0.0
    daily_pnl: float = 0.0
    open_positions: int = 0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    circuit_breaker_triggered: bool = False
    bot_running: bool = False
    risk_multiplier: float = 1.0  # from day classifier
    blocked_symbols: set = field(default_factory=set)


# Singleton risk state
_state = RiskState()


def get_risk_state() -> RiskState:
    return _state


def initialize(portfolio_value: float):
    _state.portfolio_value = portfolio_value
    _state.daily_pnl = 0.0
    _state.open_positions = 0
    _state.realized_pnl = 0.0
    _state.unrealized_pnl = 0.0
    _state.circuit_breaker_triggered = False
    logger.info(f"Risk manager initialized: portfolio=₹{portfolio_value:,.0f}")


def set_risk_multiplier(multiplier: float):
    _state.risk_multiplier = max(0.5, min(1.5, multiplier))
    logger.info(f"Risk multiplier set to {_state.risk_multiplier}")


def update_daily_pnl(realized: float, unrealized: float):
    _state.realized_pnl = realized
    _state.unrealized_pnl = unrealized
    _state.daily_pnl = realized + unrealized
    _check_circuit_breaker()


def update_position_count(count: int):
    _state.open_positions = count


def _check_circuit_breaker():
    if _state.circuit_breaker_triggered:
        return
    loss_pct = abs(_state.daily_pnl) / _state.portfolio_value * 100
    if _state.daily_pnl < 0 and loss_pct >= settings.max_daily_drawdown:
        _state.circuit_breaker_triggered = True
        logger.critical(
            f"CIRCUIT BREAKER TRIGGERED: daily loss {loss_pct:.2f}% "
            f"exceeds {settings.max_daily_drawdown}% limit"
        )


def reset_circuit_breaker():
    _state.circuit_breaker_triggered = False
    logger.info("Circuit breaker manually reset")


class RiskValidationError(Exception):
    pass


def validate_signal(signal: dict) -> tuple[bool, str]:
    """
    Validate an options signal against risk rules.
    Returns (approved, reason). Lot sizing is determined by the signal generator.
    """
    if _state.circuit_breaker_triggered:
        return False, "Circuit breaker active — no new trades"

    sig_type = signal.get("signal", "SKIP")
    if sig_type not in ("BUY_CE", "BUY_PE"):
        return False, f"Invalid signal type: {sig_type}"

    if _state.open_positions >= settings.max_positions:
        return False, f"Max positions ({settings.max_positions}) reached"

    entry   = signal.get("entry_premium")
    stop    = signal.get("stop_premium")
    target  = signal.get("target_premium")
    lots    = signal.get("lots", 1)
    lot_size = signal.get("lot_size", settings.nifty_lot_size)

    if not entry or not stop or not target:
        return False, "Missing entry_premium/stop_premium/target_premium"

    # R:R check on premium
    risk_pts   = entry - stop
    reward_pts = target - entry
    if risk_pts <= 0:
        return False, "Invalid stop — risk_pts <= 0"

    rr = reward_pts / risk_pts
    if rr < settings.min_rr_ratio:
        return False, f"R:R {rr:.2f} < minimum {settings.min_rr_ratio}"

    # Capital check
    capital_needed = entry * lots * lot_size
    max_capital = _state.portfolio_value * settings.max_premium_pct / 100
    if capital_needed > max_capital:
        return False, (
            f"Capital needed ₹{capital_needed:.0f} > limit ₹{max_capital:.0f}"
        )

    logger.info(
        f"Signal approved: {signal.get('tradingsymbol')} {sig_type} "
        f"{lots}L @ ₹{entry:.1f} SL=₹{stop:.1f} T=₹{target:.1f} R:R={rr:.2f}"
    )
    return True, "OK"


def get_risk_metrics() -> dict:
    daily_loss_pct = (
        abs(_state.daily_pnl) / _state.portfolio_value * 100
        if _state.portfolio_value else 0
    )
    budget_used = daily_loss_pct / settings.max_daily_drawdown * 100

    return {
        "portfolio_value": _state.portfolio_value,
        "daily_pnl": round(_state.daily_pnl, 2),
        "realized_pnl": round(_state.realized_pnl, 2),
        "unrealized_pnl": round(_state.unrealized_pnl, 2),
        "daily_loss_pct": round(daily_loss_pct, 2),
        "max_daily_drawdown_pct": settings.max_daily_drawdown,
        "drawdown_budget_used_pct": round(budget_used, 1),
        "open_positions": _state.open_positions,
        "max_positions": settings.max_positions,
        "circuit_breaker_triggered": _state.circuit_breaker_triggered,
        "risk_multiplier": _state.risk_multiplier,
        "bot_running": _state.bot_running,
    }
