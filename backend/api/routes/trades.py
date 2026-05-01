from fastapi import APIRouter, Query
from backend.database import supabase_db as sdb
from backend.config import settings

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
def get_trades(
    mode: str = Query(default=None),
    status: str = Query(default=None),
    limit: int = Query(default=50, le=500),
):
    trades = sdb.get_trades(
        mode=mode or settings.trading_mode,
        status=status,
        limit=limit,
    )
    return trades


@router.get("/pnl")
def get_pnl_history(mode: str = Query(default=None)):
    return sdb.get_pnl_history(mode=mode or settings.trading_mode)
