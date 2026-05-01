"""
Historical data fetcher for ML training.
Fetches NIFTY + BANKNIFTY index candles + India VIX from Kite.
Date range: April 1, 2020 → today (~6 years, covers COVID crash + full recovery).

Kite per-call limits:
  day      → 2000 candles → 2 calls per index
  5minute  → 100 days     → 23 calls per index
  1minute  → 60 days      → 37 calls per index

All saved as parquet to backend/ml/data/{interval}/{SYMBOL}.parquet
Resume-safe: skips existing files unless force=True.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from backend.core.kite_client import kite_client
from backend.utils.logger import get_logger

logger = get_logger(__name__)

DATA_DIR = Path(__file__).parent / "data"

# Fixed start — April 2020 captures COVID crash + full recovery cycle
DATA_START = datetime(2020, 4, 1)

# Instruments to fetch (index tokens resolved at runtime)
INDEX_SYMBOLS = {
    "NIFTY":     "NIFTY 50",        # NSE
    "BANKNIFTY": "NIFTY BANK",      # NSE
    "INDIA_VIX": "INDIA VIX",       # NSE
}

# Kite per-call date-range limits
INTERVAL_LIMITS = {
    "day":     1800,
    "5minute": 100,
    "1minute": 60,
}


def _data_path(interval: str, symbol: str) -> Path:
    return DATA_DIR / interval / f"{symbol}.parquet"


def _date_chunks(interval: str) -> list[tuple[str, str]]:
    limit = INTERVAL_LIMITS[interval]
    end   = datetime.now()
    start = DATA_START
    chunks, cur = [], start
    while cur < end:
        chunk_end = min(cur + timedelta(days=limit - 1), end)
        chunks.append((
            cur.strftime("%Y-%m-%d %H:%M:%S"),
            chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
        ))
        cur = chunk_end + timedelta(days=1)
    return chunks


def _build_token_map() -> dict[str, int]:
    """Resolve NSE instrument tokens for our index symbols."""
    logger.info("Fetching NSE instrument list…")
    instruments = kite_client.get_instruments("NSE")
    token_map: dict[str, int] = {}
    for inst in instruments:
        sym = inst["tradingsymbol"]
        for our_name, kite_sym in INDEX_SYMBOLS.items():
            if sym == kite_sym:
                token_map[our_name] = inst["instrument_token"]
    missing = set(INDEX_SYMBOLS) - set(token_map)
    if missing:
        logger.warning(f"Tokens not found for: {missing}")
    logger.info(f"Token map: {token_map}")
    return token_map


def fetch_symbol(
    symbol: str,
    token: int,
    interval: str,
    force: bool = False,
) -> pd.DataFrame | None:
    """Fetch all chunks for one symbol+interval, save as parquet."""
    path = _data_path(interval, symbol)
    if path.exists() and not force:
        logger.debug(f"[skip] {symbol} {interval}")
        return pd.read_parquet(path)

    chunks = _date_chunks(interval)
    frames = []
    for from_dt, to_dt in chunks:
        try:
            candles = kite_client.get_historical_data(token, from_dt, to_dt, interval)
            if candles:
                frames.append(pd.DataFrame(candles))
            time.sleep(0.35)
        except Exception as e:
            logger.error(f"{symbol} {interval} [{from_dt[:10]}]: {e}")
            time.sleep(1.0)

    if not frames:
        logger.warning(f"No data for {symbol} {interval}")
        return None

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    df["symbol"] = symbol

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    logger.info(f"Saved {len(df):,} candles → {path.name}")
    return df


def fetch_all(
    intervals: list[str] = ("day", "5minute", "1minute"),
    force: bool = False,
) -> dict[str, dict[str, pd.DataFrame]]:
    """
    Fetch all index instruments for each interval.
    Returns {interval: {symbol: DataFrame}}.
    """
    token_map = _build_token_map()
    result: dict[str, dict[str, pd.DataFrame]] = {iv: {} for iv in intervals}

    for interval in intervals:
        chunks_per = len(_date_chunks(interval))
        total_calls = len(token_map) * chunks_per
        logger.info(
            f"\n=== {interval} | {chunks_per} chunks × {len(token_map)} symbols "
            f"= {total_calls} calls | ETA ~{total_calls * 0.35 / 60:.1f} min ==="
        )
        for sym, token in tqdm(token_map.items(), desc=f"Fetching {interval}"):
            df = fetch_symbol(sym, token, interval, force=force)
            if df is not None:
                result[interval][sym] = df

    return result


def load_all(
    intervals: list[str] = ("day", "5minute", "1minute"),
) -> dict[str, dict[str, pd.DataFrame]]:
    """Load already-downloaded parquet files from disk."""
    result: dict[str, dict[str, pd.DataFrame]] = {}
    for interval in intervals:
        result[interval] = {}
        iv_dir = DATA_DIR / interval
        if not iv_dir.exists():
            continue
        for path in iv_dir.glob("*.parquet"):
            result[interval][path.stem] = pd.read_parquet(path)
    counts = {iv: len(v) for iv, v in result.items()}
    logger.info(f"Loaded from disk: {counts}")
    return result


def data_summary() -> dict:
    summary = {}
    for interval in INTERVAL_LIMITS:
        iv_dir = DATA_DIR / interval
        files = list(iv_dir.glob("*.parquet")) if iv_dir.exists() else []
        rows = 0
        for f in files:
            try:
                rows += len(pd.read_parquet(f, columns=["date"]))
            except Exception:
                pass
        summary[interval] = {"files": len(files), "total_candles": rows}
    return summary
