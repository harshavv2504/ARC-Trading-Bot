import pandas as pd
import pandas_ta as ta
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def compute_indicators(candles: list[dict]) -> dict:
    """
    Compute all TA indicators from a list of OHLCV candle dicts.
    Each candle: {date, open, high, low, close, volume}
    Returns a flat dict of latest indicator values.
    """
    if len(candles) < 30:
        logger.warning(f"Insufficient candles ({len(candles)}) for indicators")
        return {}

    df = pd.DataFrame(candles)
    df.rename(columns={"date": "datetime"}, inplace=True)
    df = df.sort_values("datetime").reset_index(drop=True)

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    result: dict = {}

    # EMAs
    result["ema9"] = _last(ta.ema(close, length=9))
    result["ema21"] = _last(ta.ema(close, length=21))
    result["ema50"] = _last(ta.ema(close, length=50))

    # RSI
    result["rsi"] = _last(ta.rsi(close, length=14))

    # MACD
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        result["macd"] = _last(macd_df.iloc[:, 0])
        result["macd_signal"] = _last(macd_df.iloc[:, 2])
        result["macd_hist"] = _last(macd_df.iloc[:, 1])

    # Bollinger Bands
    bb_df = ta.bbands(close, length=20, std=2)
    if bb_df is not None and not bb_df.empty:
        result["bb_upper"] = _last(bb_df.iloc[:, 0])
        result["bb_mid"] = _last(bb_df.iloc[:, 1])
        result["bb_lower"] = _last(bb_df.iloc[:, 2])
        result["bb_width"] = _last(bb_df.iloc[:, 3]) if bb_df.shape[1] > 3 else None

    # ATR
    result["atr"] = _last(ta.atr(high, low, close, length=14))

    # Supertrend
    st_df = ta.supertrend(high, low, close, length=10, multiplier=3)
    if st_df is not None and not st_df.empty:
        result["supertrend"] = _last(st_df.iloc[:, 0])
        result["supertrend_dir"] = int(_last(st_df.iloc[:, 1]) or 0)  # 1 bullish, -1 bearish

    # Volume ratio (current vs 20-period avg)
    vol_avg = volume.rolling(20).mean()
    if not vol_avg.empty and vol_avg.iloc[-1]:
        result["vol_ratio"] = round(float(volume.iloc[-1]) / float(vol_avg.iloc[-1]), 2)
    else:
        result["vol_ratio"] = 1.0

    # Current price
    result["current_price"] = float(close.iloc[-1])
    result["prev_close"] = float(close.iloc[-2]) if len(close) > 1 else float(close.iloc[-1])

    # Trend direction summary
    result["trend"] = _determine_trend(result)

    return {k: round(float(v), 4) if isinstance(v, (int, float)) and v is not None else v
            for k, v in result.items()}


def _last(series) -> float | None:
    if series is None or series.empty:
        return None
    val = series.dropna()
    if val.empty:
        return None
    return float(val.iloc[-1])


def _determine_trend(ind: dict) -> str:
    """Simple trend logic: EMA stack + Supertrend."""
    try:
        ema_bullish = ind["ema9"] > ind["ema21"] > ind["ema50"]
        ema_bearish = ind["ema9"] < ind["ema21"] < ind["ema50"]
        st_bull = ind.get("supertrend_dir", 0) == 1
        st_bear = ind.get("supertrend_dir", 0) == -1

        if ema_bullish and st_bull:
            return "STRONG_BULLISH"
        elif ema_bullish or st_bull:
            return "BULLISH"
        elif ema_bearish and st_bear:
            return "STRONG_BEARISH"
        elif ema_bearish or st_bear:
            return "BEARISH"
    except (TypeError, KeyError):
        pass
    return "NEUTRAL"
