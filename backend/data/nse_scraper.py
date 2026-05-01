"""
NSE data scraper — all live + historical market context for options trading.

Sources:
  NSE API   — VIX, FII/DII cash, options chain, market status
  NSE API   — FII derivatives positioning (futures L/S ratio)
  NSE       — Bhavcopy for historical F&O EOD (OI, IV per strike)
  yfinance  — global cues (Dow, Nasdaq, Nikkei, Hang Seng, Crude, USD/INR)
"""

import io
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from backend.data.cache import ttl_cache
from backend.utils.logger import get_logger

logger = get_logger(__name__)

BHAVCOPY_DIR = Path(__file__).parent.parent / "ml" / "data" / "bhavcopy"

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com",
    "Connection": "keep-alive",
}


def _nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(NSE_HEADERS)
    try:
        s.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass
    return s


# ── 1. India VIX ─────────────────────────────────────────────────────────────

@ttl_cache(ttl=300)
def get_india_vix() -> dict:
    try:
        s = _nse_session()
        r = s.get("https://www.nseindia.com/api/allIndices", timeout=10)
        r.raise_for_status()
        for idx in r.json().get("data", []):
            if idx.get("indexSymbol") == "India VIX":
                vix = float(idx.get("last", 15.0))
                return {
                    "vix": vix,
                    "change": float(idx.get("variation", 0)),
                    "pct_change": float(idx.get("percentChange", 0)),
                    "high": float(idx.get("high", vix)),
                    "low": float(idx.get("low", vix)),
                }
    except Exception as e:
        logger.error(f"VIX fetch failed: {e}")
    return {"vix": 15.0, "change": 0.0, "pct_change": 0.0, "high": 15.0, "low": 15.0}


# ── 2. FII/DII Cash Market ────────────────────────────────────────────────────

@ttl_cache(ttl=7200)
def get_fii_dii_data() -> dict:
    try:
        s = _nse_session()
        r = s.get("https://www.nseindia.com/api/fiidiiTradeReact", timeout=10)
        r.raise_for_status()
        fii_net = dii_net = 0.0
        for row in r.json():
            cat = row.get("category", "").upper()
            net = float(row.get("netPurchasesSales", 0) or 0)
            if "FII" in cat or "FPI" in cat:
                fii_net += net
            elif "DII" in cat:
                dii_net += net
        return {
            "fii_net": round(fii_net, 2),
            "dii_net": round(dii_net, 2),
            "fii_sentiment": "bullish" if fii_net > 500 else ("bearish" if fii_net < -500 else "neutral"),
            "dii_sentiment": "bullish" if dii_net > 0 else "bearish",
        }
    except Exception as e:
        logger.error(f"FII/DII fetch failed: {e}")
    return {"fii_net": 0.0, "dii_net": 0.0, "fii_sentiment": "neutral", "dii_sentiment": "neutral"}


# ── 3. FII Derivatives Positioning ───────────────────────────────────────────

@ttl_cache(ttl=7200)
def get_fii_derivatives() -> dict:
    """
    FII index futures long/short ratio.
    Ratio > 1 = FIIs net long (bullish).  < 1 = net short (bearish).
    """
    try:
        s = _nse_session()
        r = s.get(
            "https://www.nseindia.com/api/fii-derivatives-statistics",
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        fut_long = fut_short = opt_long = opt_short = 0.0
        for row in data.get("data", []):
            inst = row.get("instrumentType", "").upper()
            longs  = float(row.get("noOfContractsLong", 0) or 0)
            shorts = float(row.get("noOfContractsShort", 0) or 0)
            if "FUTURES" in inst and "INDEX" in inst:
                fut_long  += longs
                fut_short += shorts
            elif "OPTIONS" in inst and "INDEX" in inst:
                opt_long  += longs
                opt_short += shorts

        fut_ls = round(fut_long / max(fut_short, 1), 3)
        opt_ls = round(opt_long / max(opt_short, 1), 3)
        return {
            "fii_fut_long": fut_long,
            "fii_fut_short": fut_short,
            "fii_fut_ls_ratio": fut_ls,
            "fii_opt_long": opt_long,
            "fii_opt_short": opt_short,
            "fii_opt_ls_ratio": opt_ls,
            "fii_net_bias": "bullish" if fut_ls > 1.1 else ("bearish" if fut_ls < 0.9 else "neutral"),
        }
    except Exception as e:
        logger.error(f"FII derivatives fetch failed: {e}")
    return {
        "fii_fut_long": 0, "fii_fut_short": 0, "fii_fut_ls_ratio": 1.0,
        "fii_opt_long": 0, "fii_opt_short": 0, "fii_opt_ls_ratio": 1.0,
        "fii_net_bias": "neutral",
    }


# ── 4. NSE Options Chain ──────────────────────────────────────────────────────

@ttl_cache(ttl=60)
def get_options_chain(symbol: str = "NIFTY") -> dict:
    """
    Live options chain from NSE for NIFTY / BANKNIFTY / FINNIFTY.
    Computes: PCR, max pain, IV skew, ATM IV.
    """
    try:
        s = _nse_session()
        r = s.get(
            f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}",
            timeout=15,
        )
        r.raise_for_status()
        records   = r.json().get("records", {})
        underlying = float(records.get("underlyingValue", 0))
        expiries   = records.get("expiryDates", [])
        chain      = records.get("data", [])

        if not chain or not underlying:
            return _empty_chain(symbol)

        nearest_expiry = expiries[0] if expiries else None
        ce_oi = pe_oi = 0.0
        strikes: dict[float, dict] = {}
        atm_strike = None
        min_diff = float("inf")

        for row in chain:
            if nearest_expiry and row.get("expiryDate") != nearest_expiry:
                continue
            strike = float(row.get("strikePrice", 0))
            diff = abs(strike - underlying)
            if diff < min_diff:
                min_diff = diff
                atm_strike = strike

            ce = row.get("CE", {})
            pe = row.get("PE", {})
            ce_v = float(ce.get("openInterest", 0) or 0)
            pe_v = float(pe.get("openInterest", 0) or 0)
            ce_oi += ce_v
            pe_oi += pe_v

            strikes[strike] = {
                "ce_oi":     ce_v,
                "pe_oi":     pe_v,
                "ce_iv":     float(ce.get("impliedVolatility", 0) or 0),
                "pe_iv":     float(pe.get("impliedVolatility", 0) or 0),
                "ce_ltp":    float(ce.get("lastPrice", 0) or 0),
                "pe_ltp":    float(pe.get("lastPrice", 0) or 0),
                "ce_volume": float(ce.get("totalTradedVolume", 0) or 0),
                "pe_volume": float(pe.get("totalTradedVolume", 0) or 0),
                "ce_oi_chg": float(ce.get("changeinOpenInterest", 0) or 0),
                "pe_oi_chg": float(pe.get("changeinOpenInterest", 0) or 0),
            }

        pcr       = round(pe_oi / max(ce_oi, 1), 3)
        max_pain  = _compute_max_pain(strikes) if strikes else atm_strike
        iv_skew   = _compute_iv_skew(strikes, atm_strike) if strikes and atm_strike else 0.0
        atm_ce_iv, atm_pe_iv = _get_atm_iv(strikes, atm_strike)
        # Fresh OI buildup: which direction has more new OI being added
        ce_new_oi = sum(max(v["ce_oi_chg"], 0) for v in strikes.values())
        pe_new_oi = sum(max(v["pe_oi_chg"], 0) for v in strikes.values())

        return {
            "symbol": symbol,
            "underlying": underlying,
            "atm_strike": atm_strike,
            "nearest_expiry": nearest_expiry,
            "expiry_dates": expiries[:4],
            "pcr": pcr,
            "ce_total_oi": ce_oi,
            "pe_total_oi": pe_oi,
            "ce_new_oi": ce_new_oi,
            "pe_new_oi": pe_new_oi,
            "oi_bias": "bullish" if pe_new_oi > ce_new_oi * 1.2 else ("bearish" if ce_new_oi > pe_new_oi * 1.2 else "neutral"),
            "max_pain": max_pain,
            "max_pain_distance_pct": round(abs(underlying - max_pain) / underlying * 100, 2) if max_pain else 0,
            "iv_skew": iv_skew,
            "atm_ce_iv": atm_ce_iv,
            "atm_pe_iv": atm_pe_iv,
            "strikes": strikes,
        }
    except Exception as e:
        logger.error(f"Options chain fetch failed ({symbol}): {e}")
    return _empty_chain(symbol)


def _compute_max_pain(strikes: dict) -> float:
    pain = {}
    for target in strikes:
        loss = sum(
            v["ce_oi"] * max(target - s, 0) + v["pe_oi"] * max(s - target, 0)
            for s, v in strikes.items()
        )
        pain[target] = loss
    return min(pain, key=pain.get) if pain else 0.0


def _compute_iv_skew(strikes: dict, atm: float) -> float:
    d = strikes.get(atm, {})
    return round(d.get("pe_iv", 0) - d.get("ce_iv", 0), 2)


def _get_atm_iv(strikes: dict, atm: float) -> tuple[float, float]:
    d = strikes.get(atm, {})
    return d.get("ce_iv", 0.0), d.get("pe_iv", 0.0)


def _empty_chain(symbol: str) -> dict:
    return {
        "symbol": symbol, "underlying": 0.0, "atm_strike": 0.0,
        "nearest_expiry": None, "expiry_dates": [], "pcr": 1.0,
        "ce_total_oi": 0, "pe_total_oi": 0, "ce_new_oi": 0, "pe_new_oi": 0,
        "oi_bias": "neutral", "max_pain": 0.0, "max_pain_distance_pct": 0.0,
        "iv_skew": 0.0, "atm_ce_iv": 0.0, "atm_pe_iv": 0.0, "strikes": {},
    }


# ── 5. IV Rank ─────────────────────────────────────────────────────────────────

def compute_iv_rank(vix_series: pd.Series | None = None) -> dict:
    """
    IV Rank  = (current VIX - 52wk low) / (52wk high - 52wk low) * 100
    IV Pctile = % of past 252 sessions where VIX < today
    Pass vix_series (daily VIX close) for accurate computation.
    Falls back to range-based approximation if not available.
    """
    current = get_india_vix()["vix"]
    try:
        if vix_series is not None and len(vix_series) >= 20:
            yr = vix_series.iloc[-252:]
            lo = float(yr.min())
            hi = float(yr.max())
            iv_pct = round((yr < current).mean() * 100, 1)
        else:
            lo, hi = 11.0, 28.0
            iv_pct = round(min(max((current - lo) / (hi - lo) * 100, 0), 100), 1)

        iv_rank = round((current - lo) / max(hi - lo, 1) * 100, 1)
        iv_rank = max(0.0, min(100.0, iv_rank))

        return {
            "current_vix": current,
            "iv_rank": iv_rank,
            "iv_percentile": iv_pct,
            "vix_52wk_low": lo,
            "vix_52wk_high": hi,
            "premium_environment": (
                "CHEAP"          if iv_rank < 25 else
                "FAIR"           if iv_rank < 45 else
                "EXPENSIVE"      if iv_rank < 65 else
                "VERY_EXPENSIVE"
            ),
            "should_buy_options": iv_rank < 40,
        }
    except Exception as e:
        logger.error(f"IV rank failed: {e}")
    return {
        "current_vix": current, "iv_rank": 30.0, "iv_percentile": 40.0,
        "vix_52wk_low": 11.0, "vix_52wk_high": 28.0,
        "premium_environment": "FAIR", "should_buy_options": True,
    }


# ── 6. Global Cues ────────────────────────────────────────────────────────────

@ttl_cache(ttl=900)
def get_global_cues() -> dict:
    """Dow, Nasdaq, Nikkei, Hang Seng, USD/INR, Crude via yfinance."""
    try:
        import yfinance as yf
        tickers = {
            "dow": "^DJI", "nasdaq": "^IXIC", "nikkei": "^N225",
            "hangseng": "^HSI", "usdinr": "USDINR=X", "crude": "CL=F",
        }
        data = yf.download(
            list(tickers.values()), period="5d", interval="1d",
            progress=False, auto_adjust=True,
        )
        # Handle both flat and MultiIndex column structures
        if isinstance(data.columns, pd.MultiIndex):
            closes = data["Close"]
        else:
            closes = data.filter(like="Close")

        result: dict = {}
        for name, ticker in tickers.items():
            try:
                s = closes[ticker].dropna() if ticker in closes.columns else pd.Series(dtype=float)
                if len(s) >= 2:
                    prev, curr = float(s.iloc[-2]), float(s.iloc[-1])
                    result[name] = {
                        "prev_close": round(prev, 2),
                        "last": round(curr, 2),
                        "change_pct": round((curr - prev) / prev * 100, 2),
                    }
                else:
                    result[name] = {"prev_close": 0, "last": 0, "change_pct": 0}
            except Exception:
                result[name] = {"prev_close": 0, "last": 0, "change_pct": 0}

        weighted = (
            result.get("dow",    {}).get("change_pct", 0) * 0.40 +
            result.get("nasdaq", {}).get("change_pct", 0) * 0.35 +
            result.get("nikkei", {}).get("change_pct", 0) * 0.25
        )
        result["composite_change_pct"] = round(weighted, 2)
        result["global_sentiment"] = (
            "STRONGLY_POSITIVE" if weighted >  1.0 else
            "POSITIVE"          if weighted >  0.3 else
            "STRONGLY_NEGATIVE" if weighted < -1.0 else
            "NEGATIVE"          if weighted < -0.3 else
            "NEUTRAL"
        )
        return result
    except Exception as e:
        logger.error(f"Global cues failed: {e}")
    return {
        "dow": {}, "nasdaq": {}, "nikkei": {}, "hangseng": {},
        "usdinr": {}, "crude": {},
        "composite_change_pct": 0.0, "global_sentiment": "NEUTRAL",
    }


# ── 7. Event Calendar ─────────────────────────────────────────────────────────

def get_event_calendar() -> dict:
    today = date.today()

    days_ahead = (3 - today.weekday()) % 7 or 7
    next_expiry = today + timedelta(days=days_ahead)
    dte = (next_expiry - today).days
    is_monthly = (next_expiry + timedelta(days=7)).month != next_expiry.month

    rbi_dates = [
        date(2025, 2, 7), date(2025, 4, 9), date(2025, 6, 6),
        date(2025, 8, 8), date(2025, 10, 8), date(2025, 12, 5),
        date(2026, 2, 6), date(2026, 4, 8), date(2026, 6, 5),
        date(2026, 8, 7), date(2026, 10, 9), date(2026, 12, 4),
    ]
    days_to_rbi = min((
        (d - today).days for d in rbi_dates if d >= today
    ), default=999)

    return {
        "next_weekly_expiry": next_expiry.isoformat(),
        "dte": dte,
        "is_expiry_day": dte == 0,
        "is_expiry_eve": dte == 1,
        "is_monthly_expiry_week": is_monthly,
        "days_to_rbi": days_to_rbi,
        "rbi_week": days_to_rbi <= 3,
        "avoid_naked_buys": dte <= 1 or days_to_rbi <= 1,
    }


# ── 8. NSE Bhavcopy (historical F&O EOD) ─────────────────────────────────────

def download_bhavcopy(for_date: date) -> pd.DataFrame | None:
    """Download NSE F&O Bhavcopy CSV — NIFTY/BANKNIFTY options rows only."""
    if for_date.weekday() >= 5:
        return None

    BHAVCOPY_DIR.mkdir(parents=True, exist_ok=True)
    cache = BHAVCOPY_DIR / f"{for_date.isoformat()}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)

    day = for_date.strftime("%d")
    mon = for_date.strftime("%b").upper()
    yr  = for_date.strftime("%Y")
    url = (
        f"https://www1.nseindia.com/content/historical/DERIVATIVES/"
        f"{yr}/{mon}/fo{day}{mon}{yr}bhav.csv.zip"
    )
    try:
        s = _nse_session()
        r = s.get(url, timeout=20)
        if r.status_code != 200:
            return None
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            df = pd.read_csv(z.open(z.namelist()[0]))
        df.columns = [c.strip() for c in df.columns]
        df = df[df["SYMBOL"].isin(["NIFTY", "BANKNIFTY", "FINNIFTY"])]
        df = df[df["INSTRUMENT"].str.contains("OPT", na=False)]
        if not df.empty:
            df.to_parquet(cache, index=False)
        return df
    except Exception as e:
        logger.debug(f"Bhavcopy unavailable for {for_date}: {e}")
    return None


def get_historical_pcr(days: int = 30) -> pd.DataFrame:
    """Daily PCR from bhavcopy for last N trading days."""
    records = []
    today = date.today()
    for i in range(days + 15):
        d = today - timedelta(days=i + 1)
        df = download_bhavcopy(d)
        if df is None or df.empty:
            continue
        try:
            ce_oi = df[df["OPTION_TYP"] == "CE"]["OPEN_INT"].sum()
            pe_oi = df[df["OPTION_TYP"] == "PE"]["OPEN_INT"].sum()
            records.append({
                "date": d.isoformat(),
                "pcr": round(pe_oi / max(ce_oi, 1), 3),
                "ce_oi": ce_oi, "pe_oi": pe_oi,
            })
        except Exception:
            pass
        if len(records) >= days:
            break
    if not records:
        return pd.DataFrame(columns=["date", "pcr", "ce_oi", "pe_oi"])
    return pd.DataFrame(records).sort_values("date")


# ── 9. Full aggregated context ─────────────────────────────────────────────────

def get_full_market_context() -> dict:
    vix     = get_india_vix()
    fii_dii = get_fii_dii_data()
    fii_d   = get_fii_derivatives()
    iv      = compute_iv_rank()
    glb     = get_global_cues()
    events  = get_event_calendar()

    return {
        "vix": vix["vix"],
        "vix_change": vix["pct_change"],
        "vix_high": vix["high"],
        "vix_low": vix["low"],
        "iv_rank": iv["iv_rank"],
        "iv_percentile": iv["iv_percentile"],
        "premium_environment": iv["premium_environment"],
        "should_buy_options": iv["should_buy_options"],
        "fii_net": fii_dii["fii_net"],
        "dii_net": fii_dii["dii_net"],
        "fii_sentiment": fii_dii["fii_sentiment"],
        "dii_sentiment": fii_dii["dii_sentiment"],
        "fii_fut_ls_ratio": fii_d["fii_fut_ls_ratio"],
        "fii_opt_ls_ratio": fii_d["fii_opt_ls_ratio"],
        "fii_net_bias": fii_d["fii_net_bias"],
        "global_sentiment": glb.get("global_sentiment", "NEUTRAL"),
        "global_change_pct": glb.get("composite_change_pct", 0),
        "dow_change_pct": glb.get("dow", {}).get("change_pct", 0),
        "nasdaq_change_pct": glb.get("nasdaq", {}).get("change_pct", 0),
        "nikkei_change_pct": glb.get("nikkei", {}).get("change_pct", 0),
        "usdinr": glb.get("usdinr", {}).get("last", 83.0),
        "crude_change_pct": glb.get("crude", {}).get("change_pct", 0),
        "dte": events["dte"],
        "is_expiry_day": events["is_expiry_day"],
        "is_expiry_eve": events["is_expiry_eve"],
        "next_weekly_expiry": events["next_weekly_expiry"],
        "rbi_week": events["rbi_week"],
        "avoid_naked_buys": events["avoid_naked_buys"],
    }
