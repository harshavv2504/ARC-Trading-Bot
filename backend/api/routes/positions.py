from fastapi import APIRouter
from backend.database import supabase_db as sdb
from backend.config import settings

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
def get_positions():
    return sdb.get_positions(mode=settings.trading_mode)
