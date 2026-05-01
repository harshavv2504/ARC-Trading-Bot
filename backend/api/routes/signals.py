from datetime import date
from fastapi import APIRouter, Query
from backend.database import supabase_db as sdb

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
def get_signals(limit: int = Query(default=50, le=200)):
    return sdb.get_signals(limit=limit)


@router.get("/day-classification")
def get_day_classification():
    dc = sdb.get_today_classification()
    if not dc:
        return {"classification": "PENDING", "score": None, "date": date.today().isoformat()}
    return {
        "date":           dc.get("date"),
        "score":          dc.get("score"),
        "buy_side_score": dc.get("buy_side_score"),
        "classification": dc.get("classification"),
        "vix":            dc.get("vix"),
        "iv_rank":        dc.get("iv_rank"),
        "premium_env":    dc.get("premium_environment"),
        "fii_net":        dc.get("fii_net"),
        "fii_fut_ls_ratio": dc.get("fii_fut_ls_ratio"),
        "dii_net":        dc.get("dii_net"),
        "pcr":            dc.get("pcr"),
        "nifty_gap":      dc.get("nifty_gap"),
        "global_sentiment": dc.get("global_sentiment"),
        "ml_direction":   dc.get("ml_direction"),
        "ml_regime":      dc.get("ml_regime"),
        "key_reasons":    dc.get("reasons_json", []),
    }
