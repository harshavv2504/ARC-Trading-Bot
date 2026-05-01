"""
Day Classifier — Options buy-side focused.
Produces both a general market score (1-10) and a buy_side_score (0-10)
specifically for buying index options (CE/PE) that day.
"""

import json
from backend.ai.llm_client import chat_json
from backend.ai.sentiment_engine import build_market_context
from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an expert NSE India options trader with 20 years of experience.
You ONLY buy index options (NIFTY/BANKNIFTY calls or puts). You NEVER sell options.
Classify each trading day for option buying suitability.
Always respond with valid JSON only — no markdown, no text outside the JSON."""

DAY_CLASSIFY_PROMPT = """Analyze these NSE India market indicators for index options BUY-SIDE trading.

=== Market Conditions ===
- India VIX: {vix:.2f} ({vix_level}) | 5d change: {vix_change:+.2f}%
- IV Rank: {iv_rank:.1f}% | Premium environment: {premium_environment}
- Should buy options today: {should_buy_options}

=== Institutional Flow ===
- FII Net Cash: ₹{fii_net:.0f} Cr
- FII Futures L/S Ratio: {fii_fut_ls_ratio:.2f}
- DII Net Cash: ₹{dii_net:.0f} Cr

=== Options Data ===
- NIFTY Gap: {nifty_gap_pct:+.2f}%
- PCR (OI): {put_call_ratio:.2f}
- Max Pain: {max_pain:.0f} | OI Bias: {oi_bias}
- ATM CE IV: {atm_ce_iv:.1f}% | ATM PE IV: {atm_pe_iv:.1f}%

=== Global Cues ===
- Global sentiment: {global_sentiment}
- Composite change: {composite_change_pct:+.2f}%

=== Calendar ===
- Event calendar: {event_summary}
- ML direction: {ml_direction} | Trade side: {ml_trade_side}

Based on these indicators, classify today for INDEX OPTIONS BUYING (not selling).

Key rules:
- IV Rank > 40%: options are EXPENSIVE → penalize buy-side score
- IV Rank < 20%: options are CHEAP → reward buy-side score
- VIX > 25: high uncertainty → reduce position size
- Strong FII buying + ML bullish → prefer CE buys
- Strong FII selling + ML bearish → prefer PE buys
- Expiry day or avoid_naked_buys=true → penalize heavily

Return ONLY this JSON (no extra text):
{{
  "score": <float 1.0-10.0 — overall day tradability>,
  "buy_side_score": <float 0.0-10.0 — suitability for BUYING options specifically>,
  "classification": "<GOOD|NEUTRAL|BAD>",
  "preferred_side": "<CE|PE|EITHER|SKIP>",
  "aggressiveness": "<HIGH|MEDIUM|LOW|AVOID>",
  "key_reasons": ["<reason1>", "<reason2>", "<reason3>"],
  "max_positions_recommendation": <int 1-5>,
  "risk_multiplier": <float 0.5-1.5>,
  "summary": "<one sentence summary for buy-side options>"
}}"""


def classify_day(market_ctx: dict) -> dict:
    """Classify today's day for options buy-side trading."""
    try:
        # Build safe format dict with defaults for missing keys
        fmt = {
            "vix":                  market_ctx.get("vix", 15.0),
            "vix_level":            market_ctx.get("vix_level", "NORMAL"),
            "vix_change":           market_ctx.get("vix_change_1d", 0.0),
            "iv_rank":              market_ctx.get("iv_rank", 25.0),
            "premium_environment":  market_ctx.get("premium_environment", "FAIR"),
            "should_buy_options":   market_ctx.get("should_buy_options", True),
            "fii_net":              market_ctx.get("fii_net", 0.0),
            "fii_fut_ls_ratio":     market_ctx.get("fii_fut_ls_ratio", 1.0),
            "dii_net":              market_ctx.get("dii_net", 0.0),
            "nifty_gap_pct":        market_ctx.get("nifty_gap_pct", 0.0),
            "put_call_ratio":       market_ctx.get("put_call_ratio", 1.0),
            "max_pain":             market_ctx.get("max_pain", 0),
            "oi_bias":              market_ctx.get("oi_bias", "NEUTRAL"),
            "atm_ce_iv":            market_ctx.get("atm_ce_iv", 15.0),
            "atm_pe_iv":            market_ctx.get("atm_pe_iv", 15.0),
            "global_sentiment":     market_ctx.get("global_sentiment", "NEUTRAL"),
            "composite_change_pct": market_ctx.get("composite_change_pct", 0.0),
            "event_summary":        _event_summary(market_ctx),
            "ml_direction":         market_ctx.get("ml_direction", "FLAT"),
            "ml_trade_side":        market_ctx.get("ml_trade_side") or "NONE",
        }

        prompt = DAY_CLASSIFY_PROMPT.format(**fmt)
        result = chat_json(SYSTEM_PROMPT, prompt, max_tokens=600, model=settings.ai_model_day)
        result["_raw_ctx"] = market_ctx

        logger.info(
            f"Day classified: {result['classification']} "
            f"score={result['score']} buy_score={result.get('buy_side_score')} "
            f"preferred={result.get('preferred_side')}"
        )
        return result

    except Exception as e:
        logger.error(f"Day classification failed: {e}")
        return _fallback(market_ctx)


def _event_summary(ctx: dict) -> str:
    parts = []
    if ctx.get("is_expiry_day"):
        parts.append("EXPIRY DAY")
    if ctx.get("is_expiry_eve"):
        parts.append("expiry eve")
    if ctx.get("avoid_naked_buys"):
        parts.append("avoid naked buys")
    dte = ctx.get("days_to_expiry")
    if dte is not None:
        parts.append(f"{dte}d to expiry")
    if ctx.get("rbi_week"):
        parts.append("RBI policy week")
    return ", ".join(parts) if parts else "normal"


def _fallback(ctx: dict) -> dict:
    vix       = ctx.get("vix", 15)
    fii       = ctx.get("fii_net", 0)
    iv_rank   = ctx.get("iv_rank", 25)
    avoid     = ctx.get("avoid_naked_buys", False)

    if avoid or iv_rank > 50:
        score, buy_score, cls = 3.0, 2.0, "BAD"
    elif vix < 15 and fii > 0 and iv_rank < 30:
        score, buy_score, cls = 7.5, 8.0, "GOOD"
    elif vix > 22 or fii < -2000:
        score, buy_score, cls = 3.0, 3.5, "BAD"
    else:
        score, buy_score, cls = 5.0, 5.0, "NEUTRAL"

    return {
        "score":                       score,
        "buy_side_score":              buy_score,
        "classification":              cls,
        "preferred_side":              "EITHER",
        "aggressiveness":              "MEDIUM" if cls == "GOOD" else "LOW",
        "key_reasons":                 ["Fallback rule-based (AI unavailable)"],
        "max_positions_recommendation": 2,
        "risk_multiplier":             1.0,
        "summary":                     f"Rule-based: {cls}. VIX={vix} IV_rank={iv_rank}",
        "_raw_ctx":                    ctx,
    }
