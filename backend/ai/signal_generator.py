"""
Options Signal Generator — buy-side only (CE / PE).

Outputs specific option contracts with entry/target/stop in PREMIUM terms.
Never generates sell/short signals.

Signal format:
  {
    "signal":        "BUY_CE" | "BUY_PE" | "SKIP",
    "index":         "NIFTY" | "BANKNIFTY",
    "option_type":   "CE" | "PE",
    "strike":        24000,
    "expiry":        "2026-05-01",
    "lot_size":      25,
    "lots":          1,
    "entry_premium": 120.0,     # price to buy the option at
    "target_premium": 240.0,    # exit at 2x (default)
    "stop_premium":  60.0,      # exit if premium drops 50%
    "max_loss":      ₹1500,     # lots × lot_size × stop_premium
    "confidence":    8.2,
    "reasoning":     "...",
    "key_signals":   [...],
  }
"""

from backend.ai.llm_client import chat_json
from backend.config import settings
from backend.core.market_data import (
    get_live_options_chain, select_strike, build_option_symbol, get_next_expiry,
    LOT_SIZES,
)
from backend.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an expert NSE India options trader specialising in index options.
You ONLY buy options (CE or PE) — never sell or short.

Your edge: catching directional moves on NIFTY/BANKNIFTY with carefully timed option buys.
You protect capital aggressively: stop loss = 50% of premium paid, target = 2x premium.

STRICT RULES:
- Only recommend BUY_CE, BUY_PE, or SKIP
- Entry premium must be realistic (check the provided chain data)
- Never recommend deep OTM options (stick to ATM or 1 strike OTM max)
- If conviction is below 7/10, recommend SKIP
- Theta is your enemy — only enter when there's a clear catalyst or momentum
- Return ONLY valid JSON — no markdown, no text outside JSON"""

SIGNAL_PROMPT = """Generate an index options trade signal.

=== MARKET CONTEXT ===
Index: {index} | Spot: ₹{spot:.0f} | ATM Strike: {atm_strike}
Day Score: {buy_side_score}/10 | Premium Environment: {premium_environment}
VIX: {vix:.1f} | IV Rank: {iv_rank:.1f}% | ATM CE IV: {atm_ce_iv:.1f}% | ATM PE IV: {atm_pe_iv:.1f}%
PCR: {pcr:.2f} ({pcr_signal}) | IV Skew: {iv_skew:+.2f}
Max Pain: {max_pain:.0f} | Distance from Max Pain: {max_pain_distance_pct:.1f}%
OI Bias: {oi_bias}

=== DIRECTION SIGNALS ===
ML Direction: {ml_direction} (confidence: {ml_confidence:.0%})
Bull Probability: {bull_prob:.0%} | Bear Probability: {bear_prob:.0%}
Regime: {regime} | Strategy: {regime_strategy}
Global Markets: {global_sentiment} ({global_change_pct:+.2f}%)
FII Futures L/S: {fii_fut_ls_ratio:.2f} | FII Bias: {fii_net_bias}
Gap: {nifty_gap_pct:+.2f}% ({gap_signal})

=== TECHNICAL (5-min index chart) ===
Trend: {trend} | EMA9: {ema9:.0f} | EMA21: {ema21:.0f} | EMA50: {ema50:.0f}
RSI: {rsi:.1f} | MACD Hist: {macd_hist:.2f} | ADX: {adx:.1f}
BB Position: {bb_pos:.2f} (0=lower, 1=upper) | ATR: {atr:.0f} pts

=== AVAILABLE OPTIONS (nearest expiry: {expiry}) ===
ATM CE ({atm_strike}CE) premium: ₹{atm_ce_ltp:.1f}
ATM PE ({atm_strike}PE) premium: ₹{atm_pe_ltp:.1f}
1-OTM CE ({otm_ce_strike}CE) premium: ₹{otm_ce_ltp:.1f}
1-OTM PE ({otm_pe_strike}PE) premium: ₹{otm_pe_ltp:.1f}

=== PORTFOLIO ===
Open Positions: {open_positions}/{max_positions}
Daily Risk Budget: ₹{risk_budget_remaining:.0f}
Today P&L: ₹{daily_pnl:+.0f}
DTE: {dte} days

Return ONLY this JSON:
{{
  "signal": "<BUY_CE|BUY_PE|SKIP>",
  "index": "{index}",
  "option_type": "<CE|PE|null>",
  "strike": <int or null>,
  "moneyness": "<ATM|SLIGHTLY_OTM>",
  "lots": <int 1-3>,
  "entry_premium": <float or null>,
  "target_premium": <float or null>,
  "stop_premium": <float or null>,
  "confidence": <float 1-10>,
  "time_horizon": "<intraday|positional>",
  "reasoning": "<2-3 sentences explaining the setup>",
  "key_signals": ["<signal1>", "<signal2>", "<signal3>"],
  "skip_reason": "<why skipping, or null>"
}}"""


def generate_signal(
    index: str,
    indicators: dict,
    day_classification: dict,
    ml_direction: dict,
    ml_regime: dict,
    market_ctx: dict,
    portfolio_state: dict,
) -> dict:
    """
    Generate a specific options buy signal.
    All parameters come from the pipeline orchestrator.
    """
    if not indicators:
        return _skip(index, "insufficient_indicator_data")

    # Hard skip conditions
    buy_score = day_classification.get("buy_side_score", 5)
    if buy_score < 3:
        return _skip(index, f"buy_side_score_too_low:{buy_score}")

    if market_ctx.get("avoid_naked_buys"):
        return _skip(index, "event_risk_avoid_naked_buys")

    if not ml_regime.get("should_buy_options"):
        return _skip(index, f"regime_says_avoid:{ml_regime.get('regime')}")

    # Get live options chain
    chain = get_live_options_chain(index)
    if not chain or not chain.get("spot"):
        return _skip(index, "options_chain_unavailable")

    spot         = chain["spot"]
    atm_strike   = chain["atm_strike"]
    expiry_dt    = get_next_expiry(index)
    expiry_str   = expiry_dt.strftime("%Y-%m-%d") if expiry_dt else "unknown"
    lot_size     = LOT_SIZES.get(index, 25)

    # Extract ATM and 1-OTM premiums from chain
    from backend.core.market_data import STRIKE_GAP
    gap = STRIKE_GAP.get(index, 50)
    strikes      = chain.get("strikes", {})
    otm_ce_strike = atm_strike + gap
    otm_pe_strike = atm_strike - gap

    atm_ce_ltp  = strikes.get(atm_strike, {}).get("ce_ltp", 0)
    atm_pe_ltp  = strikes.get(atm_strike, {}).get("pe_ltp", 0)
    otm_ce_ltp  = strikes.get(otm_ce_strike, {}).get("ce_ltp", 0)
    otm_pe_ltp  = strikes.get(otm_pe_strike, {}).get("pe_ltp", 0)

    prompt = SIGNAL_PROMPT.format(
        index=index,
        spot=spot,
        atm_strike=int(atm_strike),
        buy_side_score=buy_score,
        premium_environment=market_ctx.get("premium_environment", "FAIR"),
        vix=market_ctx.get("vix", 15),
        iv_rank=market_ctx.get("iv_rank", 30),
        atm_ce_iv=market_ctx.get("atm_ce_iv", 0),
        atm_pe_iv=market_ctx.get("atm_pe_iv", 0),
        pcr=market_ctx.get("pcr", 1.0),
        pcr_signal=market_ctx.get("pcr_signal", "neutral"),
        iv_skew=market_ctx.get("iv_skew", 0),
        max_pain=market_ctx.get("max_pain", atm_strike),
        max_pain_distance_pct=market_ctx.get("max_pain_distance_pct", 0),
        oi_bias=market_ctx.get("oi_bias", "neutral"),
        ml_direction=ml_direction.get("direction", "FLAT"),
        ml_confidence=ml_direction.get("confidence", 0),
        bull_prob=ml_direction.get("bull_prob", 0),
        bear_prob=ml_direction.get("bear_prob", 0),
        regime=ml_regime.get("regime", "MED_VOL"),
        regime_strategy=ml_regime.get("strategy", "selective"),
        global_sentiment=market_ctx.get("global_sentiment", "NEUTRAL"),
        global_change_pct=market_ctx.get("global_change_pct", 0),
        fii_fut_ls_ratio=market_ctx.get("fii_fut_ls_ratio", 1.0),
        fii_net_bias=market_ctx.get("fii_net_bias", "neutral"),
        nifty_gap_pct=market_ctx.get("nifty_gap_pct", 0),
        gap_signal=market_ctx.get("gap_signal", "flat_open"),
        trend=indicators.get("trend", "NEUTRAL"),
        ema9=indicators.get("ema9", spot),
        ema21=indicators.get("ema21", spot),
        ema50=indicators.get("ema50", spot),
        rsi=indicators.get("rsi", 50),
        macd_hist=indicators.get("macd_hist", 0),
        adx=indicators.get("adx", 20),
        bb_pos=indicators.get("bb_pos", 0.5),
        atr=indicators.get("atr", 50),
        expiry=expiry_str,
        atm_ce_ltp=atm_ce_ltp,
        atm_pe_ltp=atm_pe_ltp,
        otm_ce_strike=int(otm_ce_strike),
        otm_ce_ltp=otm_ce_ltp,
        otm_pe_strike=int(otm_pe_strike),
        otm_pe_ltp=otm_pe_ltp,
        open_positions=portfolio_state.get("open_positions", 0),
        max_positions=settings.max_positions,
        risk_budget_remaining=portfolio_state.get("risk_budget_remaining", 0),
        daily_pnl=portfolio_state.get("daily_pnl", 0),
        dte=market_ctx.get("dte", 7),
    )

    try:
        result = chat_json(SYSTEM_PROMPT, prompt, max_tokens=600, model=settings.ai_model_signal)

        if result.get("signal") == "SKIP":
            return _skip(index, result.get("skip_reason", "llm_skip"))

        # Validate and enrich the signal
        option_type = result.get("option_type")
        strike      = result.get("strike", atm_strike)
        lots        = max(1, min(int(result.get("lots", 1)), 3))
        entry_prem  = result.get("entry_premium") or (atm_ce_ltp if option_type == "CE" else atm_pe_ltp)
        target_prem = result.get("target_premium") or round(entry_prem * settings.option_target_multiplier, 1)
        stop_prem   = result.get("stop_premium")   or round(entry_prem * (1 - settings.option_stop_loss_pct / 100), 1)
        lot_size_   = lot_size
        max_loss    = round(stop_prem * lots * lot_size_, 2) if stop_prem else None

        # Option tradingsymbol
        tradingsymbol = build_option_symbol(index, expiry_dt, strike, option_type) if expiry_dt else None

        result.update({
            "index":          index,
            "tradingsymbol":  tradingsymbol,
            "expiry":         expiry_str,
            "lot_size":       lot_size_,
            "lots":           lots,
            "entry_premium":  entry_prem,
            "target_premium": target_prem,
            "stop_premium":   stop_prem,
            "max_loss":       max_loss,
            "spot":           spot,
            "indicators":     indicators,
        })

        confidence = result.get("confidence", 0)
        if confidence < 7:
            return _skip(index, f"confidence_too_low:{confidence}")

        logger.info(
            f"Signal: {index} {result['signal']} {tradingsymbol} "
            f"entry=₹{entry_prem} target=₹{target_prem} stop=₹{stop_prem} "
            f"lots={lots} max_loss=₹{max_loss} conf={confidence}"
        )
        return result

    except Exception as e:
        logger.error(f"Signal generation failed ({index}): {e}")
        return _skip(index, f"llm_error:{str(e)[:80]}")


def _skip(index: str, reason: str) -> dict:
    return {
        "signal":         "SKIP",
        "index":          index,
        "option_type":    None,
        "strike":         None,
        "tradingsymbol":  None,
        "lots":           0,
        "entry_premium":  None,
        "target_premium": None,
        "stop_premium":   None,
        "max_loss":       None,
        "confidence":     0.0,
        "reasoning":      reason,
        "key_signals":    [],
        "skip_reason":    reason,
    }
