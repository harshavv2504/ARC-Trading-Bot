"""
ARC Trading Bot — ML Training Pipeline
=======================================
Fetches NIFTY + BANKNIFTY + VIX historical data from Kite,
then trains three models for index options buy-side trading.

Usage:
    python -m backend.ml.train                  # Full pipeline
    python -m backend.ml.train --skip-fetch     # Use existing data
    python -m backend.ml.train --force-fetch    # Re-download all data
    python -m backend.ml.train --model day      # Train only direction model
    python -m backend.ml.train --model regime   # Train only regime model
    python -m backend.ml.train --model timing   # Train only timing model

Models trained:
  1. Direction  (XGBoost)     — NIFTY direction: STRONG_UP/UP/FLAT/DOWN/STRONG_DOWN
  2. Regime     (RandomForest) — Volatility regime: LOW_VOL/MED_VOL/HIGH_VOL/SPIKE/TRENDING/RANGING
  3. Timing     (GBM)         — Entry timing: ENTER/WAIT (1-min candles)

Data: NIFTY + BANKNIFTY + INDIA VIX from Apr 2020 → today (~6 years)
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pandas as pd

from backend.ml.data_fetcher import fetch_all, load_all, data_summary
from backend.ml.day_model    import train as train_day,    DayModel
from backend.ml.regime_model import train as train_regime, RegimeModel
from backend.ml.timing_model import train as train_timing, TimingModel
from backend.utils.logger    import get_logger

logger = get_logger("ml.train")


def _build_vix_series(daily_data: dict) -> pd.Series | None:
    """Extract India VIX daily close as a Series indexed by date."""
    vix_df = daily_data.get("INDIA_VIX")
    if vix_df is None or vix_df.empty:
        logger.warning("No VIX data available — training without IV rank features")
        return None
    vix = vix_df.set_index("date")["close"]
    vix.index = pd.to_datetime(vix.index)
    logger.info(f"VIX series: {len(vix)} days | {vix.index[0].date()} → {vix.index[-1].date()}")
    return vix


def run(
    skip_fetch:  bool = False,
    force_fetch: bool = False,
    model:       str  = "all",
):
    logger.info("=" * 60)
    logger.info("ARC ML Training Pipeline — Index Options Buy-Side")
    logger.info("=" * 60)

    # ── Step 1: Data ─────────────────────────────────────────────────────────
    if skip_fetch:
        logger.info("Loading data from disk (--skip-fetch)…")
        all_data = load_all(["day", "5minute", "1minute"])
    else:
        logger.info(f"Current data: {data_summary()}")
        needed = []
        if model in ("all", "day"):    needed.append("day")
        if model in ("all", "regime"): needed.append("5minute")
        if model in ("all", "timing"): needed.extend(["5minute", "1minute"])
        needed = list(dict.fromkeys(needed))

        logger.info(f"Fetching intervals: {needed}")
        t0 = time.time()
        all_data = fetch_all(intervals=needed, force=force_fetch)
        logger.info(f"Fetch complete in {(time.time()-t0)/60:.1f} min")

    # ── Step 2: VIX series ────────────────────────────────────────────────────
    vix_series = _build_vix_series(all_data.get("day", {}))

    # Filter out VIX from OHLCV data passed to models (keep only index candles)
    day_data = {k: v for k, v in all_data.get("day", {}).items() if k != "INDIA_VIX"}
    fivemin_data = {k: v for k, v in all_data.get("5minute", {}).items() if k != "INDIA_VIX"}
    onemin_data  = {k: v for k, v in all_data.get("1minute", {}).items()  if k != "INDIA_VIX"}

    if not day_data:
        logger.error("No index daily data found. Check Kite auth and re-run.")
        return

    # ── Step 3: Train Direction Model ─────────────────────────────────────────
    if model in ("all", "day"):
        logger.info("\n── Training Direction Model (XGBoost 5-class) ──")
        t0 = time.time()
        train_day(day_data, vix_series=vix_series)
        logger.info(f"Direction model done in {time.time()-t0:.1f}s")
    else:
        if DayModel.exists():
            logger.info("Direction model exists — skipping (use --model all to retrain)")

    # ── Step 4: Train Regime Model ────────────────────────────────────────────
    if model in ("all", "regime"):
        if not fivemin_data:
            logger.error("No 5-min data for regime model. Re-run without --skip-fetch.")
        else:
            logger.info("\n── Training Regime Model (RandomForest 7-class) ──")
            t0 = time.time()
            train_regime(fivemin_data)
            logger.info(f"Regime model done in {time.time()-t0:.1f}s")
    else:
        if RegimeModel.exists():
            logger.info("Regime model exists — skipping")

    # ── Step 5: Train Timing Model ────────────────────────────────────────────
    if model in ("all", "timing"):
        if not onemin_data:
            logger.warning("No 1-min data for timing model — skipping timing model")
        else:
            logger.info("\n── Training Timing Model (GBM binary) ──")
            t0 = time.time()
            train_timing(onemin_data)
            logger.info(f"Timing model done in {time.time()-t0:.1f}s")
    else:
        if TimingModel.exists():
            logger.info("Timing model exists — skipping")

    # ── Step 6: Sanity check ──────────────────────────────────────────────────
    logger.info("\n── Sanity Check ──")
    _sanity_check()

    logger.info("\n" + "=" * 60)
    logger.info("Training complete! Models saved to backend/ml/models/")
    logger.info("Start the bot: uvicorn backend.main:app --reload")
    logger.info("=" * 60)


def _sanity_check():
    import numpy as np
    n = 80
    prices = 24000 + np.cumsum(np.random.randn(n) * 50)
    dummy = pd.DataFrame({
        "date":   pd.date_range("2024-01-01 09:15", periods=n, freq="5min"),
        "open":   prices,
        "high":   prices + np.abs(np.random.randn(n) * 30),
        "low":    prices - np.abs(np.random.randn(n) * 30),
        "close":  prices + np.random.randn(n) * 20,
        "volume": np.random.randint(500000, 2000000, n),
    })

    if DayModel.exists():
        dm  = DayModel.load()
        res = dm.predict(dummy)
        logger.info(f"Direction model: {res['direction']} (conf={res['confidence']})")

    if RegimeModel.exists():
        rm  = RegimeModel.load()
        res = rm.predict(dummy)
        logger.info(f"Regime model: {res['regime']} (conf={res['confidence']})")

    if TimingModel.exists():
        tm  = TimingModel.load()
        res = tm.predict(dummy)
        logger.info(f"Timing model: {res['decision']} (prob={res['probability']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ARC ML Training Pipeline")
    parser.add_argument("--skip-fetch",  action="store_true", help="Use existing parquet files")
    parser.add_argument("--force-fetch", action="store_true", help="Re-download all data")
    parser.add_argument("--model", choices=["all", "day", "regime", "timing"], default="all")
    args = parser.parse_args()
    run(skip_fetch=args.skip_fetch, force_fetch=args.force_fetch, model=args.model)
