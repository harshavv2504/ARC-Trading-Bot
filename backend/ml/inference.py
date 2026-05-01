"""
Real-time ML inference — all three models loaded once at startup.

Models:
  DayModel    → direction: STRONG_UP / UP / FLAT / DOWN / STRONG_DOWN
  RegimeModel → volatility regime: LOW_VOL / MED_VOL / HIGH_VOL / SPIKE / TRENDING_* / RANGING
  TimingModel → entry timing: ENTER / WAIT

Fallbacks to rule-based logic when models aren't trained yet.
"""

import pandas as pd

from backend.ml.day_model    import DayModel
from backend.ml.regime_model import RegimeModel
from backend.ml.timing_model import TimingModel
from backend.utils.logger    import get_logger

logger = get_logger(__name__)

_day_model:    DayModel    | None = None
_regime_model: RegimeModel | None = None
_timing_model: TimingModel | None = None
_models_available: bool = False


def load_models() -> bool:
    global _day_model, _regime_model, _timing_model, _models_available

    loaded = []
    for name, cls, setter in [
        ("day",    DayModel,    lambda m: globals().__setitem__("_day_model",    m)),
        ("regime", RegimeModel, lambda m: globals().__setitem__("_regime_model", m)),
        ("timing", TimingModel, lambda m: globals().__setitem__("_timing_model", m)),
    ]:
        if cls.exists():
            try:
                obj = cls.load()
                if name == "day":    _day_model    = obj
                if name == "regime": _regime_model = obj
                if name == "timing": _timing_model = obj
                loaded.append(name)
            except Exception as e:
                logger.error(f"{name} model load failed: {e}")
        else:
            logger.warning(f"{name} model not found — run: python -m backend.ml.train")

    _models_available = len(loaded) >= 2  # at minimum day + regime
    if _models_available:
        logger.info(f"ML models loaded: {loaded} — Stage 2 gate ACTIVE")
    else:
        logger.warning("ML models not ready — using rule-based fallback")
    return _models_available


def get_direction(daily_candles: pd.DataFrame, vix_series: pd.Series | None = None) -> dict:
    """
    Predict NIFTY/BANKNIFTY direction for today.
    Returns {direction, trade_side, confidence, bull_prob, bear_prob, is_strong}.
    """
    if _day_model is None:
        return _fallback_direction(daily_candles)
    return _day_model.predict(daily_candles, vix_series=vix_series)


def get_regime(fivemin_candles: pd.DataFrame) -> dict:
    """
    Classify current volatility regime from 5-min candles.
    Returns {regime, strategy, should_buy_options, size_multiplier, confidence}.
    """
    if _regime_model is None:
        return _fallback_regime(fivemin_candles)
    return _regime_model.predict(fivemin_candles)


def get_entry_timing(onemin_candles: pd.DataFrame) -> dict:
    """
    Should we enter the options trade RIGHT NOW?
    Returns {decision, probability, enter_now}.
    """
    if _timing_model is None:
        return {"decision": "ENTER", "probability": 0.6, "enter_now": True, "reason": "no_timing_model"}
    return _timing_model.predict(onemin_candles)


def models_ready() -> bool:
    return _models_available


# ── Rule-based fallbacks ──────────────────────────────────────────────────────

def _fallback_direction(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 5:
        return {"direction": "FLAT", "trade_side": None, "confidence": 0.0,
                "bull_prob": 0.0, "bear_prob": 0.0, "is_strong": False, "reason": "no_data"}

    closes = df["close"]
    ret5 = closes.pct_change(5).iloc[-1] * 100 if len(closes) >= 5 else 0
    ema9  = closes.ewm(span=9).mean().iloc[-1]
    ema21 = closes.ewm(span=21).mean().iloc[-1]

    if ret5 > 1.0 and ema9 > ema21:
        direction, side, strong = "STRONG_UP", "CE", True
    elif ret5 > 0.4:
        direction, side, strong = "UP", "CE", False
    elif ret5 < -1.0 and ema9 < ema21:
        direction, side, strong = "STRONG_DOWN", "PE", True
    elif ret5 < -0.4:
        direction, side, strong = "DOWN", "PE", False
    else:
        direction, side, strong = "FLAT", None, False

    return {
        "direction": direction, "trade_side": side, "confidence": 0.6,
        "bull_prob": 0.6 if side == "CE" else 0.2,
        "bear_prob": 0.6 if side == "PE" else 0.2,
        "is_strong": strong, "reason": "fallback_rule",
    }


def _fallback_regime(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 30:
        return {
            "regime": "MED_VOL", "strategy": "buy_selectively",
            "should_buy_options": True, "size_multiplier": 0.75,
            "confidence": 0.5, "reason": "no_data",
        }

    closes = df["close"]
    atr    = (df["high"] - df["low"]).rolling(14).mean()
    atr_ratio = (atr / closes).iloc[-1]
    atr_80    = (atr / closes).quantile(0.80)
    ema9  = closes.ewm(span=9).mean()
    ema21 = closes.ewm(span=21).mean()

    if atr_ratio > atr_80 * 1.5:
        regime, buy, mult = "SPIKE",       False, 0.0
    elif atr_ratio > atr_80:
        regime, buy, mult = "HIGH_VOL",    True,  0.6
    elif ema9.iloc[-1] > ema21.iloc[-1] and ema9.pct_change(3).iloc[-1] > 0:
        regime, buy, mult = "TRENDING_UP", True,  1.1
    elif ema9.iloc[-1] < ema21.iloc[-1] and ema9.pct_change(3).iloc[-1] < 0:
        regime, buy, mult = "TRENDING_DOWN", True, 1.1
    else:
        regime, buy, mult = "MED_VOL",    True,  1.0

    strategy_map = {
        "TRENDING_UP": "buy_CE_momentum", "TRENDING_DOWN": "buy_PE_momentum",
        "HIGH_VOL": "reduce_size", "SPIKE": "avoid",
        "MED_VOL": "buy_selectively", "LOW_VOL": "buy_aggressively",
    }
    return {
        "regime": regime, "strategy": strategy_map.get(regime, "buy_selectively"),
        "should_buy_options": buy, "size_multiplier": mult,
        "confidence": 0.6, "reason": "fallback_rule",
    }
