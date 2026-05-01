"""
Feature engineering for index options trading ML models.
Designed for NIFTY / BANKNIFTY index candles.
"""

import numpy as np
import pandas as pd
import pandas_ta as ta

MIN_ROWS = 60

VIX_FEATURE_COLS = ["vix", "vix_rank", "vix_pct", "hv_iv_ratio", "vix_change_1d", "vix_5d_avg"]


def compute_features(df: pd.DataFrame, vix_series: pd.Series | None = None) -> pd.DataFrame:
    """
    Compute all TA + volatility features on OHLCV DataFrame.
    vix_series: daily VIX close values (enables IV rank features).
    """
    df = df.copy().sort_values("date").reset_index(drop=True)
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]

    # ── Trend ────────────────────────────────────────────────────────────────
    df["ema9"]  = ta.ema(c, length=9)
    df["ema21"] = ta.ema(c, length=21)
    df["ema50"] = ta.ema(c, length=50)
    df["ema200"] = ta.ema(c, length=200)

    df["ema_bull"] = (
        (df["ema9"] > df["ema21"]).astype(int) +
        (df["ema21"] > df["ema50"]).astype(int)
    )
    df["above_ema200"] = (c > df["ema200"]).astype(int)
    df["ema9_slope"]   = df["ema9"].pct_change(3) * 100
    df["ema21_slope"]  = df["ema21"].pct_change(5) * 100

    # ── Momentum ─────────────────────────────────────────────────────────────
    df["rsi14"] = ta.rsi(c, length=14)
    df["rsi9"]  = ta.rsi(c, length=9)

    macd_df = ta.macd(c, fast=12, slow=26, signal=9)
    if macd_df is not None and not macd_df.empty:
        df["macd"]      = macd_df.iloc[:, 0]
        df["macd_hist"] = macd_df.iloc[:, 1]
        df["macd_sig"]  = macd_df.iloc[:, 2]
    else:
        df["macd"] = df["macd_hist"] = df["macd_sig"] = np.nan

    stoch = ta.stoch(h, l, c, k=14, d=3)
    if stoch is not None and not stoch.empty:
        df["stoch_k"] = stoch.iloc[:, 0]
        df["stoch_d"] = stoch.iloc[:, 1]
    else:
        df["stoch_k"] = df["stoch_d"] = np.nan

    # ── Volatility ───────────────────────────────────────────────────────────
    df["atr14"]    = ta.atr(h, l, c, length=14)
    df["atr_ratio"] = df["atr14"] / c.replace(0, np.nan)

    bb = ta.bbands(c, length=20, std=2)
    if bb is not None and not bb.empty:
        df["bb_upper"] = bb.iloc[:, 0]
        df["bb_lower"] = bb.iloc[:, 2]
        df["bb_mid"]   = bb.iloc[:, 1]
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, np.nan)
        df["bb_pos"]   = (c - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"] + 1e-9)
    else:
        df["bb_upper"] = df["bb_lower"] = df["bb_mid"] = np.nan
        df["bb_width"] = df["bb_pos"] = np.nan

    log_ret = np.log(c / c.shift(1))
    df["hv20"] = log_ret.rolling(20).std() * np.sqrt(252) * 100

    # ── Trend Strength ───────────────────────────────────────────────────────
    adx_df = ta.adx(h, l, c, length=14)
    if adx_df is not None and not adx_df.empty:
        df["adx"]     = adx_df.iloc[:, 0]
        df["dmp"]     = adx_df.iloc[:, 1]
        df["dmn"]     = adx_df.iloc[:, 2]
        df["di_diff"] = df["dmp"] - df["dmn"]
    else:
        df["adx"] = df["dmp"] = df["dmn"] = df["di_diff"] = np.nan

    # ── Volume ───────────────────────────────────────────────────────────────
    vol_ma = v.rolling(20).mean()
    df["vol_ratio"] = v / vol_ma.replace(0, np.nan)
    df["vol_spike"] = (df["vol_ratio"] > 2.0).astype(int)
    obv = ta.obv(c, v)
    df["obv_slope"] = obv.pct_change(5) if obv is not None else np.nan

    # ── Price Structure ───────────────────────────────────────────────────────
    df["ret1"]   = c.pct_change(1)  * 100
    df["ret5"]   = c.pct_change(5)  * 100
    df["ret20"]  = c.pct_change(20) * 100
    df["ret_open"] = (c - df["open"]) / df["open"].replace(0, np.nan) * 100

    df["high_low_range"] = (h - l) / df["open"].replace(0, np.nan) * 100
    df["body_pct"]       = abs(c - df["open"]) / (h - l + 1e-9)

    df["dist_from_20d_high"] = (c - h.rolling(20).max()) / c * 100
    df["dist_from_20d_low"]  = (c - l.rolling(20).min()) / c * 100

    # ── VIX Features ─────────────────────────────────────────────────────────
    if vix_series is not None and len(vix_series) > 20:
        df = _add_vix_features(df, vix_series)
    else:
        for col in VIX_FEATURE_COLS:
            df[col] = np.nan

    # ── Calendar ─────────────────────────────────────────────────────────────
    dt = pd.to_datetime(df["date"])
    df["day_of_week"]  = dt.dt.dayofweek
    df["month"]        = dt.dt.month
    df["is_monday"]    = (dt.dt.dayofweek == 0).astype(int)
    df["is_friday"]    = (dt.dt.dayofweek == 4).astype(int)
    df["hour"]         = dt.dt.hour
    df["is_morning"]   = (dt.dt.hour < 11).astype(int)
    df["is_afternoon"] = (dt.dt.hour >= 13).astype(int)

    return df


def _add_vix_features(df: pd.DataFrame, vix_series: pd.Series) -> pd.DataFrame:
    vix_df = pd.DataFrame({"vix": vix_series.values}, index=vix_series.index)
    vix_df.index = pd.to_datetime(vix_df.index)

    vix_df["vix_rank"] = vix_df["vix"].rolling(252, min_periods=20).apply(
        lambda x: (x[-1] - x.min()) / max(x.max() - x.min(), 1) * 100
    )
    vix_df["vix_pct"] = vix_df["vix"].rolling(252, min_periods=20).apply(
        lambda x: (x[:-1] < x[-1]).mean() * 100
    )
    vix_df["vix_change_1d"] = vix_df["vix"].pct_change(1) * 100
    vix_df["vix_5d_avg"]    = vix_df["vix"].rolling(5).mean()

    df_dates = pd.to_datetime(df["date"]).dt.date
    vix_by_date = vix_df.copy()
    vix_by_date.index = vix_by_date.index.date

    for col in ["vix", "vix_rank", "vix_pct", "vix_change_1d", "vix_5d_avg"]:
        df[col] = df_dates.map(vix_by_date[col]).values

    df["hv_iv_ratio"] = df["hv20"] / df["vix"].replace(0, np.nan)
    return df


# ── Feature lists per model ────────────────────────────────────────────────────

DAY_MODEL_FEATURES = [
    "ema_bull", "above_ema200", "ema9_slope", "ema21_slope",
    "rsi14", "macd_hist", "di_diff",
    "atr_ratio", "bb_width", "hv20",
    "vol_ratio",
    "ret1", "ret5", "ret20",
    "high_low_range",
    "vix_rank", "vix_change_1d", "hv_iv_ratio",
    "day_of_week", "month",
]

REGIME_MODEL_FEATURES = [
    "ema_bull", "ema9_slope",
    "rsi14", "rsi9", "macd_hist", "stoch_k",
    "atr_ratio", "bb_width", "bb_pos",
    "adx", "dmp", "dmn", "di_diff",
    "vol_ratio", "vol_spike",
    "ret1", "ret5", "high_low_range", "body_pct",
    "day_of_week", "hour", "is_morning",
]

TIMING_MODEL_FEATURES = [
    "ema_bull", "ema9_slope",
    "rsi9", "macd_hist",
    "atr_ratio", "bb_pos",
    "vol_ratio", "vol_spike",
    "ret1", "ret5",
    "body_pct",
    "hour", "is_morning",
]


# ── Labels ────────────────────────────────────────────────────────────────────

def label_direction(df: pd.DataFrame, horizon: int = 1, threshold_pct: float = 0.5) -> pd.Series:
    """
    5-class forward direction label.
    horizon=1 on daily → next day's direction.
    threshold_pct: % move to call it UP/DOWN (not FLAT).
    """
    fwd_ret = df["close"].pct_change(horizon).shift(-horizon) * 100
    th = threshold_pct
    conditions = [
        fwd_ret > th * 2,
        fwd_ret > th,
        fwd_ret < -th * 2,
        fwd_ret < -th,
    ]
    choices = ["STRONG_UP", "UP", "STRONG_DOWN", "DOWN"]
    return pd.Series(
        np.select(conditions, choices, default="FLAT"),
        index=df.index,
        name="label_direction",
    )


def label_go_nogo(df: pd.DataFrame, min_range_pct: float = 0.7) -> pd.Series:
    """Binary GO (1) if next bar's intraday range is large enough to profit from options."""
    next_range = df["high_low_range"].shift(-1)
    next_atr   = df["atr_ratio"].shift(-1)
    atr_cap    = df["atr_ratio"].quantile(0.97)
    return ((next_range >= min_range_pct) & (next_atr <= atr_cap)).astype(int).rename("label_go")


def label_regime(df: pd.DataFrame) -> pd.Series:
    """
    7-class volatility-aware regime label.
    SPIKE / HIGH_VOL / TRENDING_UP / TRENDING_DOWN / RANGING / LOW_VOL / MED_VOL
    """
    atr_25 = df["atr_ratio"].quantile(0.25)
    atr_60 = df["atr_ratio"].quantile(0.60)
    atr_85 = df["atr_ratio"].quantile(0.85)
    atr_97 = df["atr_ratio"].quantile(0.97)
    bb_35  = df["bb_width"].quantile(0.35)

    conditions = [
        df["atr_ratio"] > atr_97,
        df["atr_ratio"] > atr_85,
        (df["adx"] > 25) & (df["ema_bull"] == 2),
        (df["adx"] > 25) & (df["ema_bull"] == 0),
        (df["adx"] < 18) & (df["bb_width"] < bb_35),
        df["atr_ratio"] < atr_25,
        (df["atr_ratio"] >= atr_25) & (df["atr_ratio"] < atr_60),
    ]
    choices = ["SPIKE", "HIGH_VOL", "TRENDING_UP", "TRENDING_DOWN", "RANGING", "LOW_VOL", "MED_VOL"]
    return pd.Series(
        np.select(conditions, choices, default="MED_VOL"),
        index=df.index,
        name="label_regime",
    )


def label_entry_timing(df: pd.DataFrame, horizon: int = 15, threshold_pct: float = 0.4) -> pd.Series:
    """Binary ENTER (1) if price moves > threshold% in next horizon bars (1-min candles)."""
    fwd_move = df["close"].pct_change(horizon).shift(-horizon).abs() * 100
    return (fwd_move > threshold_pct).astype(int).rename("label_entry")


DIRECTION_CLASSES = ["STRONG_UP", "UP", "FLAT", "DOWN", "STRONG_DOWN"]
REGIME_CLASSES    = ["LOW_VOL", "MED_VOL", "HIGH_VOL", "SPIKE", "TRENDING_UP", "TRENDING_DOWN", "RANGING"]
