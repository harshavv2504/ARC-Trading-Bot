"""
Stage 1: Rule-Based Hard Filters for Options Buy-Side Trading
==============================================================
Deterministic, zero-latency, zero API cost.
A single FAIL short-circuits the entire pipeline for that signal.

Gates are ordered cheapest → most expensive check.
"""

from backend.data.nse_scraper import get_india_vix, compute_iv_rank, get_event_calendar
from backend.risk.risk_manager import get_risk_state
from backend.config import settings
from backend.utils.market_hours import is_market_open
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Hard limits — override any ML/LLM recommendation
VIX_ABSOLUTE_MAX   = 30.0   # India VIX above this → sit out entirely (premium too expensive)
VIX_CAUTION        = 20.0   # Above this → reduce size
IV_RANK_MAX        = 40.0   # IV Rank above this → options overpriced, skip buying
MIN_DTE            = 4      # Never buy options expiring within 4 days (theta crush)
MAX_PAIN_PROXIMITY = 1.0    # % — skip if spot within 1% of max pain (pinning risk)
MIN_VOL_RATIO      = 0.4    # Skip if volume < 40% of normal (illiquid)
MIN_CANDLE_RANGE   = 0.05   # % — skip near-zero range candles (halted)


# ── Session Gate (runs once at 9:00 AM) ──────────────────────────────────────

def session_gate() -> tuple[bool, str]:
    """
    Should we trade at all today?
    Returns (ok, reason).
    """
    state = get_risk_state()

    if state.circuit_breaker_triggered:
        return False, "circuit_breaker_active"
    if not is_market_open():
        return False, "market_closed"
    if not state.bot_running:
        return False, "bot_not_running"

    # Absolute VIX limit
    vix = get_india_vix()["vix"]
    if vix >= VIX_ABSOLUTE_MAX:
        logger.warning(f"Session BLOCKED: VIX={vix:.1f} ≥ {VIX_ABSOLUTE_MAX}")
        return False, f"vix_too_high:{vix:.1f}"

    # Daily loss circuit
    if state.portfolio_value > 0:
        loss_pct = abs(min(state.daily_pnl, 0)) / state.portfolio_value * 100
        if loss_pct >= settings.max_daily_drawdown:
            return False, f"daily_loss_limit:{loss_pct:.1f}%"

    # Max positions
    if state.open_positions >= settings.max_positions:
        return False, f"max_positions:{state.open_positions}"

    # Event calendar checks
    events = get_event_calendar()
    if events["is_expiry_day"]:
        return False, "expiry_day_no_new_buys"

    return True, "ok"


# ── Options-Specific IV Gate ──────────────────────────────────────────────────

def iv_gate() -> tuple[bool, str]:
    """
    Should we be buying options right now based on IV environment?
    Runs once at start of session and cached.
    Returns (ok, reason).
    """
    iv_data = compute_iv_rank()
    iv_rank = iv_data["iv_rank"]
    events  = get_event_calendar()

    if iv_rank > IV_RANK_MAX:
        logger.info(f"IV gate BLOCKED: IV Rank={iv_rank:.1f} > {IV_RANK_MAX} (expensive premium)")
        return False, f"iv_rank_too_high:{iv_rank:.1f}"

    if events["is_expiry_eve"]:
        logger.info("IV gate CAUTION: expiry eve — theta spikes, reducing buys")
        return True, f"expiry_eve_caution"

    if events["rbi_week"]:
        logger.info("IV gate CAUTION: RBI week — IV elevated, reduce size")
        return True, "rbi_week_caution"

    return True, "ok"


# ── DTE Gate ─────────────────────────────────────────────────────────────────

def dte_gate() -> tuple[bool, str]:
    """
    Never buy options with too few days to expiry — theta will kill the trade.
    """
    events = get_event_calendar()
    dte = events["dte"]
    if dte < MIN_DTE:
        return False, f"dte_too_low:{dte}_days"
    return True, "ok"


# ── Max Pain Gate (per signal) ────────────────────────────────────────────────

def max_pain_gate(
    spot: float,
    max_pain: float,
    direction: str,  # "CE" or "PE"
) -> tuple[bool, str]:
    """
    Avoid buying options when spot is pinned near max pain.
    Max pain acts as a gravitational centre — market makers defend it.
    Also: don't buy CE when spot is above max pain, don't buy PE when below.
    """
    if not max_pain or not spot:
        return True, "ok"

    distance_pct = abs(spot - max_pain) / spot * 100

    if distance_pct < MAX_PAIN_PROXIMITY:
        return False, f"near_max_pain:{distance_pct:.2f}%"

    # Directional alignment with max pain
    if direction == "CE" and spot > max_pain * 1.02:
        return False, "spot_above_max_pain_ce_risky"
    if direction == "PE" and spot < max_pain * 0.98:
        return False, "spot_below_max_pain_pe_risky"

    return True, "ok"


# ── Symbol/Candle Gate ────────────────────────────────────────────────────────

def symbol_gate(
    symbol: str,
    candles: list[dict] | None,
) -> tuple[bool, str]:
    """Quick sanity checks on candle data."""
    state = get_risk_state()

    if symbol in state.blocked_symbols:
        return False, "symbol_blocked_today"
    if not candles or len(candles) < 10:
        return False, "insufficient_candle_data"

    last = candles[-1]
    try:
        rng_pct = (last["high"] - last["low"]) / last["open"] * 100
        if rng_pct < MIN_CANDLE_RANGE:
            return False, f"zero_range_candle:{rng_pct:.3f}%"
    except (KeyError, ZeroDivisionError):
        return False, "candle_data_malformed"

    return True, "ok"


# ── VIX context summary (for Stage 2 / LLM) ──────────────────────────────────

def get_vix_context() -> dict:
    vix_data = get_india_vix()
    iv_data  = compute_iv_rank()
    vix = vix_data.get("vix", 15.0)
    return {
        "vix":             vix,
        "vix_change_pct":  vix_data.get("pct_change", 0.0),
        "iv_rank":         iv_data["iv_rank"],
        "iv_percentile":   iv_data["iv_percentile"],
        "premium_env":     iv_data["premium_environment"],
        "vix_level": (
            "extreme_fear" if vix >= VIX_ABSOLUTE_MAX else
            "high_fear"    if vix >= VIX_CAUTION else
            "moderate"     if vix >= 14 else
            "low_fear"
        ),
        "caution_mode":       vix >= VIX_CAUTION,
        "size_cap_from_vix":  0.5 if vix >= VIX_CAUTION else 1.0,
    }
