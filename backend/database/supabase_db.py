"""
Supabase REST database layer.
All DB operations go through supabase-py (HTTPS) — no direct TCP needed.
"""

from datetime import date, datetime
from functools import lru_cache
from typing import Any

from supabase import create_client, Client

from backend.config import settings
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_client() -> Client:
    if not settings.supabase_url or not settings.supabase_key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set in .env")
    return create_client(settings.supabase_url, settings.supabase_key)


def _sb() -> Client:
    return get_client()


def _d(v: Any) -> Any:
    """Convert date/datetime to ISO string for Supabase REST."""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def _clean(data: dict) -> dict:
    return {k: _d(v) for k, v in data.items() if v is not None}


# ── Trades ─────────────────────────────────────────────────────────────────

def create_trade(data: dict) -> dict:
    payload = _clean(data)
    res = _sb().table("trades").insert(payload).execute()
    return res.data[0] if res.data else {}


def update_trade(trade_id: int, data: dict) -> dict:
    payload = _clean(data)
    res = _sb().table("trades").update(payload).eq("id", trade_id).execute()
    return res.data[0] if res.data else {}


def get_trade(trade_id: int) -> dict | None:
    res = _sb().table("trades").select("*").eq("id", trade_id).execute()
    return res.data[0] if res.data else None


def get_trades(mode: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    q = _sb().table("trades").select("*")
    if mode:
        q = q.eq("mode", mode)
    if status:
        q = q.eq("status", status)
    res = q.order("entry_time", desc=True).limit(limit).execute()
    return res.data or []


def get_open_trades(mode: str = "paper") -> list[dict]:
    return get_trades(mode=mode, status="open", limit=200)


# ── Positions ──────────────────────────────────────────────────────────────

def create_position(data: dict) -> dict:
    payload = _clean(data)
    res = _sb().table("positions").insert(payload).execute()
    return res.data[0] if res.data else {}


def update_position(position_id: int, data: dict) -> dict:
    payload = _clean(data)
    res = _sb().table("positions").update(payload).eq("id", position_id).execute()
    return res.data[0] if res.data else {}


def delete_position(position_id: int) -> None:
    _sb().table("positions").delete().eq("id", position_id).execute()


def get_positions(mode: str | None = None) -> list[dict]:
    q = _sb().table("positions").select("*")
    if mode:
        q = q.eq("mode", mode)
    res = q.order("opened_at", desc=True).execute()
    return res.data or []


def get_position_by_symbol(symbol: str, mode: str = "paper") -> dict | None:
    res = (
        _sb().table("positions")
        .select("*")
        .eq("symbol", symbol)
        .eq("mode", mode)
        .execute()
    )
    return res.data[0] if res.data else None


# ── Signals ────────────────────────────────────────────────────────────────

def create_signal(data: dict) -> dict:
    payload = _clean(data)
    res = _sb().table("signals").insert(payload).execute()
    return res.data[0] if res.data else {}


def mark_signal_executed(signal_id: int) -> None:
    _sb().table("signals").update({"executed": True}).eq("id", signal_id).execute()


def get_signals(limit: int = 50) -> list[dict]:
    res = (
        _sb().table("signals").select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ── Day Classifications ────────────────────────────────────────────────────

def upsert_day_classification(data: dict) -> dict:
    payload = _clean(data)
    res = (
        _sb().table("day_classifications")
        .upsert(payload, on_conflict="date")
        .execute()
    )
    return res.data[0] if res.data else {}


def get_today_classification() -> dict | None:
    today = date.today().isoformat()
    res = (
        _sb().table("day_classifications")
        .select("*")
        .eq("date", today)
        .execute()
    )
    return res.data[0] if res.data else None


def get_recent_classifications(days: int = 30) -> list[dict]:
    res = (
        _sb().table("day_classifications")
        .select("*")
        .order("date", desc=True)
        .limit(days)
        .execute()
    )
    return res.data or []


# ── PnL Snapshots ──────────────────────────────────────────────────────────

def create_pnl_snapshot(data: dict) -> dict:
    payload = _clean(data)
    res = _sb().table("pnl_snapshots").insert(payload).execute()
    return res.data[0] if res.data else {}


def get_pnl_history(mode: str | None = None, limit: int = 365) -> list[dict]:
    q = _sb().table("pnl_snapshots").select("*")
    if mode:
        q = q.eq("mode", mode)
    res = q.order("date", desc=False).limit(limit).execute()
    return res.data or []


def get_today_pnl(mode: str = "paper") -> dict | None:
    today = date.today().isoformat()
    res = (
        _sb().table("pnl_snapshots")
        .select("*")
        .eq("date", today)
        .eq("mode", mode)
        .execute()
    )
    return res.data[0] if res.data else None


# ── Bot Config ─────────────────────────────────────────────────────────────

def get_config(key: str) -> str | None:
    res = _sb().table("bot_config").select("value").eq("key", key).execute()
    return res.data[0]["value"] if res.data else None


def set_config(key: str, value: str) -> None:
    _sb().table("bot_config").upsert(
        {"key": key, "value": str(value)}, on_conflict="key"
    ).execute()


def get_all_config() -> dict:
    res = _sb().table("bot_config").select("key,value").execute()
    return {row["key"]: row["value"] for row in (res.data or [])}
