from backend.risk.risk_manager import get_risk_state, _state
from backend.utils.logger import get_logger

logger = get_logger(__name__)

_emergency_callbacks: list = []


def register_emergency_callback(fn):
    """Register a coroutine/function to call on emergency stop."""
    _emergency_callbacks.append(fn)


async def trigger_emergency_stop(reason: str = "Manual"):
    """Trigger emergency stop: halt bot + fire all close-position callbacks."""
    _state.circuit_breaker_triggered = True
    _state.bot_running = False
    logger.critical(f"EMERGENCY STOP: {reason}")
    for cb in _emergency_callbacks:
        try:
            import asyncio
            if asyncio.iscoroutinefunction(cb):
                await cb(reason)
            else:
                cb(reason)
        except Exception as e:
            logger.error(f"Emergency callback error: {e}")


def is_triggered() -> bool:
    return get_risk_state().circuit_breaker_triggered
