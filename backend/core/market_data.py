"""
Live market data from Kite Connect.
Index OHLCV, options chain, LTP, instrument lookup.
"""

import math
from datetime import datetime, timedelta

from backend.core.kite_client import kite_client
from backend.data.cache import ttl_cache
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Index instrument keys for Kite quotes
INDEX_INSTRUMENTS = {
    "NIFTY":     "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "SENSEX":    "BSE:SENSEX",
    "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
}

# F&O exchange symbol (used for options chain)
FNO_UNDERLYING = {
    "NIFTY":     "NIFTY",
    "BANKNIFTY": "BANKNIFTY",
    "FINNIFTY":  "FINNIFTY",
}

# Lot sizes (as of 2024 revision — update if NSE changes them)
LOT_SIZES = {
    "NIFTY":     25,
    "BANKNIFTY": 30,
    "FINNIFTY":  40,
}

# Strike intervals
STRIKE_GAP = {
    "NIFTY":     50,
    "BANKNIFTY": 100,
    "FINNIFTY":  50,
}


# ── Index live data ────────────────────────────────────────────────────────────

@ttl_cache(ttl=5)
def get_index_ltp(index: str = "NIFTY") -> float:
    """Get latest traded price for index."""
    instrument = INDEX_INSTRUMENTS.get(index, INDEX_INSTRUMENTS["NIFTY"])
    try:
        data = kite_client.kite.ltp([instrument])
        return float(data[instrument]["last_price"])
    except Exception as e:
        logger.error(f"Index LTP failed ({index}): {e}")
        return 0.0


@ttl_cache(ttl=5)
def get_index_ohlc(index: str = "NIFTY") -> dict:
    """Get today's OHLC for the index."""
    instrument = INDEX_INSTRUMENTS.get(index, INDEX_INSTRUMENTS["NIFTY"])
    try:
        data = kite_client.kite.ohlc([instrument])
        d = data[instrument]
        return {
            "open": d["ohlc"]["open"],
            "high": d["ohlc"]["high"],
            "low":  d["ohlc"]["low"],
            "close": d["ohlc"]["close"],
            "last_price": d["last_price"],
        }
    except Exception as e:
        logger.error(f"Index OHLC failed ({index}): {e}")
        return {}


def get_index_candles(
    index: str,
    interval: str = "5minute",
    days: int = 5,
) -> list[dict]:
    """
    Fetch historical candles for an index.
    Returns list of {date, open, high, low, close, volume}.
    """
    try:
        instruments = kite_client.get_instruments("NSE")
        token = None
        target_sym = {"NIFTY": "NIFTY 50", "BANKNIFTY": "NIFTY BANK", "FINNIFTY": "NIFTY FIN SERVICE"}.get(index, index)
        for inst in instruments:
            if inst["tradingsymbol"] == target_sym and inst["exchange"] == "NSE":
                token = inst["instrument_token"]
                break

        if not token:
            logger.error(f"No token found for index {index}")
            return []

        end = datetime.now()
        start = end - timedelta(days=days)
        candles = kite_client.get_historical_data(
            token,
            start.strftime("%Y-%m-%d %H:%M:%S"),
            end.strftime("%Y-%m-%d %H:%M:%S"),
            interval,
        )
        return candles
    except Exception as e:
        logger.error(f"Index candles failed ({index}, {interval}): {e}")
        return []


# ── Options chain from Kite ────────────────────────────────────────────────────

@ttl_cache(ttl=30)
def get_live_options_chain(index: str = "NIFTY", num_strikes: int = 10) -> dict:
    """
    Build options chain from Kite instruments + LTP data.
    Returns ATM strike, CE/PE LTP for ±num_strikes around ATM.
    """
    try:
        spot = get_index_ltp(index)
        if not spot:
            return {}

        strike_gap = STRIKE_GAP.get(index, 50)
        atm = round(spot / strike_gap) * strike_gap

        # Build instrument list for ±10 strikes
        expiry = get_next_expiry(index)
        if not expiry:
            return {}

        # Load NFO instruments and filter
        nfo_instruments = kite_client.get_instruments("NFO")
        expiry_str = expiry.strftime("%Y-%m-%d")

        strikes_data: dict[float, dict] = {}
        instrument_keys = []
        instrument_map: dict[str, tuple[float, str]] = {}

        for inst in nfo_instruments:
            sym = inst.get("name", "")
            if sym != FNO_UNDERLYING.get(index, index):
                continue
            exp = inst.get("expiry", "")
            if hasattr(exp, "strftime"):
                exp = exp.strftime("%Y-%m-%d")
            if str(exp) != expiry_str:
                continue
            strike = float(inst.get("strike", 0))
            if abs(strike - atm) > strike_gap * num_strikes:
                continue
            opt_type = inst.get("instrument_type", "")
            if opt_type not in ("CE", "PE"):
                continue

            key = f"NFO:{inst['tradingsymbol']}"
            instrument_keys.append(key)
            instrument_map[key] = (strike, opt_type)

        if not instrument_keys:
            return {}

        # Batch LTP fetch (Kite max 500 per call)
        ltp_data = {}
        for i in range(0, len(instrument_keys), 499):
            batch = instrument_keys[i:i + 499]
            ltp_data.update(kite_client.kite.ltp(batch))

        for key, (strike, opt_type) in instrument_map.items():
            ltp = ltp_data.get(key, {}).get("last_price", 0) or 0
            if strike not in strikes_data:
                strikes_data[strike] = {"ce_ltp": 0.0, "pe_ltp": 0.0}
            if opt_type == "CE":
                strikes_data[strike]["ce_ltp"] = ltp
            else:
                strikes_data[strike]["pe_ltp"] = ltp

        return {
            "index": index,
            "spot": spot,
            "atm_strike": atm,
            "expiry": expiry_str,
            "lot_size": LOT_SIZES.get(index, 25),
            "strikes": strikes_data,
        }
    except Exception as e:
        logger.error(f"Live options chain failed ({index}): {e}")
        return {}


def get_next_expiry(index: str = "NIFTY") -> datetime | None:
    """Get nearest expiry date for an index from NFO instruments."""
    try:
        instruments = kite_client.get_instruments("NFO")
        today = datetime.now().date()
        underlying = FNO_UNDERLYING.get(index, index)
        expiries = set()

        for inst in instruments:
            if inst.get("name") == underlying and inst.get("instrument_type") in ("CE", "PE"):
                exp = inst.get("expiry")
                if exp:
                    if hasattr(exp, "date"):
                        exp = exp.date()
                    elif isinstance(exp, str):
                        exp = datetime.strptime(exp, "%Y-%m-%d").date()
                    if exp >= today:
                        expiries.add(exp)

        if expiries:
            nearest = min(expiries)
            return datetime.combine(nearest, datetime.min.time())
    except Exception as e:
        logger.error(f"Next expiry fetch failed ({index}): {e}")
    return None


def get_option_ltp(tradingsymbol: str) -> float:
    """Get LTP for a specific option contract."""
    try:
        key = f"NFO:{tradingsymbol}"
        data = kite_client.kite.ltp([key])
        return float(data[key]["last_price"])
    except Exception as e:
        logger.error(f"Option LTP failed ({tradingsymbol}): {e}")
        return 0.0


# ── Option strike selection ────────────────────────────────────────────────────

def select_strike(
    index: str,
    direction: str,        # "CE" or "PE"
    spot: float,
    expected_move_pts: float = 0,
    moneyness: str = "ATM",  # ATM | SLIGHTLY_OTM | OTM
) -> float:
    """
    Select appropriate strike for buying.
    ATM: nearest to spot
    SLIGHTLY_OTM: 1 strike away from ATM in direction
    OTM: 2 strikes away
    """
    gap = STRIKE_GAP.get(index, 50)
    atm = round(spot / gap) * gap

    offsets = {"ATM": 0, "SLIGHTLY_OTM": 1, "OTM": 2}
    offset = offsets.get(moneyness, 0) * gap

    if direction == "CE":
        return atm + offset
    else:
        return atm - offset


def build_option_symbol(
    index: str,
    expiry: datetime,
    strike: float,
    option_type: str,  # CE | PE
) -> str:
    """
    Build NFO tradingsymbol. e.g. NIFTY25APR24000CE
    """
    exp_str = expiry.strftime("%d%b%y").upper()
    return f"{index}{exp_str}{int(strike)}{option_type}"


# ── Generic LTP ───────────────────────────────────────────────────────────────

def get_ltp(instruments: tuple | list) -> dict:
    try:
        return kite_client.kite.ltp(list(instruments))
    except Exception as e:
        logger.error(f"LTP fetch failed: {e}")
        return {}


# ── Pre-market gap ─────────────────────────────────────────────────────────────

@ttl_cache(ttl=300)
def get_nifty_premarket_gap() -> float:
    """Gap % between today's open and yesterday's close."""
    try:
        candles = get_index_candles("NIFTY", interval="day", days=3)
        if len(candles) >= 2:
            prev_close = float(candles[-2]["close"])
            today_open = float(candles[-1]["open"])
            return round((today_open - prev_close) / prev_close * 100, 2)
    except Exception as e:
        logger.error(f"Pre-market gap failed: {e}")
    return 0.0


# ── PCR from live chain ────────────────────────────────────────────────────────

@ttl_cache(ttl=60)
def compute_put_call_ratio(index: str = "NIFTY") -> float:
    from backend.data.nse_scraper import get_options_chain
    chain = get_options_chain(index)
    return chain.get("pcr", 1.0)
