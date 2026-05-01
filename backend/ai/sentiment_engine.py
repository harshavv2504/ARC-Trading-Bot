"""
Aggregates all market context for options buy-side decision making.
Combines: VIX + IV rank + FII positioning + global cues + options chain + events.
"""

from backend.data.nse_scraper import get_full_market_context, get_options_chain
from backend.core.market_data import get_nifty_premarket_gap
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def build_market_context(index: str = "NIFTY") -> dict:
    """Full market context snapshot for day classifier and signal generator."""
    ctx   = get_full_market_context()
    chain = get_options_chain(index)

    ctx.update({
        "pcr":                   chain.get("pcr", 1.0),
        "atm_ce_iv":             chain.get("atm_ce_iv", 0.0),
        "atm_pe_iv":             chain.get("atm_pe_iv", 0.0),
        "iv_skew":               chain.get("iv_skew", 0.0),
        "max_pain":              chain.get("max_pain", 0.0),
        "max_pain_distance_pct": chain.get("max_pain_distance_pct", 0.0),
        "oi_bias":               chain.get("oi_bias", "neutral"),
        "underlying":            chain.get("underlying", 0.0),
        "atm_strike":            chain.get("atm_strike", 0.0),
    })

    ctx["nifty_gap_pct"] = get_nifty_premarket_gap()
    ctx["gap_signal"] = (
        "gap_up"   if ctx["nifty_gap_pct"] >  0.3 else
        "gap_down" if ctx["nifty_gap_pct"] < -0.3 else
        "flat_open"
    )
    ctx["vix_level"]  = _vix_level(ctx["vix"])
    ctx["pcr_signal"] = _pcr_signal(ctx["pcr"])
    ctx["fii_flow"]   = (
        "buying"  if ctx["fii_net"] >  500 else
        "selling" if ctx["fii_net"] < -500 else
        "neutral"
    )
    ctx["buy_side_score"] = _compute_buy_side_score(ctx)

    logger.info(
        f"Market ctx: VIX={ctx['vix']} IV_Rank={ctx['iv_rank']} "
        f"PCR={ctx['pcr']} Gap={ctx['nifty_gap_pct']:+.2f}% "
        f"Global={ctx['global_sentiment']} BuyScore={ctx['buy_side_score']}"
    )
    return ctx


def _compute_buy_side_score(ctx: dict) -> float:
    """
    Score 0–10 for how good conditions are to buy options today.
    High score = cheap premium + clear direction + no event risk.
    """
    score = 5.0

    # IV environment (most important)
    iv_rank = ctx.get("iv_rank", 30)
    if iv_rank < 20:   score += 2.0
    elif iv_rank < 35: score += 1.0
    elif iv_rank > 55: score -= 2.0
    elif iv_rank > 40: score -= 1.0

    # Global cues — clear direction = options will move
    if abs(ctx.get("global_change_pct", 0)) > 1.0:  score += 1.0
    elif abs(ctx.get("global_change_pct", 0)) > 0.5: score += 0.5

    # FII directional conviction
    if abs(ctx.get("fii_fut_ls_ratio", 1.0) - 1.0) > 0.2: score += 0.5

    # VIX sweet spot (13–20 = enough vol for move, not too expensive)
    vix = ctx.get("vix", 15)
    if 13 <= vix <= 20:  score += 0.5
    elif vix > 25:       score -= 1.5
    elif vix < 11:       score -= 0.5

    # Event risk
    if ctx.get("is_expiry_eve"):   score -= 1.0
    if ctx.get("rbi_week"):        score -= 0.5
    if ctx.get("avoid_naked_buys"): score -= 1.5

    # PCR extreme (contrarian signal = big move likely)
    pcr = ctx.get("pcr", 1.0)
    if pcr > 1.5 or pcr < 0.5: score += 0.5

    return round(max(0.0, min(10.0, score)), 1)


def _vix_level(vix: float) -> str:
    if vix < 12:  return "very_low_fear"
    if vix < 15:  return "low_fear"
    if vix < 20:  return "moderate_fear"
    if vix < 25:  return "high_fear"
    return "extreme_fear"


def _pcr_signal(pcr: float) -> str:
    if pcr > 1.5:  return "extreme_bullish_contrarian"
    if pcr > 1.2:  return "bullish_contrarian"
    if pcr > 0.8:  return "neutral"
    if pcr > 0.5:  return "bearish_contrarian"
    return "extreme_bearish_contrarian"
