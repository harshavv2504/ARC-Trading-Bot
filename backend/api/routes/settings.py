from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from backend.database import supabase_db as sdb
from backend.config import settings
from backend.core.kite_client import kite_client

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ConfigUpdate(BaseModel):
    key: str
    value: str


@router.get("")
def get_settings():
    return {
        "trading_mode":       settings.trading_mode,
        "portfolio_value":    settings.portfolio_value,
        "max_risk_per_trade": settings.max_risk_per_trade,
        "max_daily_drawdown": settings.max_daily_drawdown,
        "max_positions":      settings.max_positions,
        "min_rr_ratio":       settings.min_rr_ratio,
        "squareoff_time":     settings.squareoff_time,
        "index_universe":     settings.index_universe,
        "max_iv_rank":        settings.max_iv_rank,
        "min_dte":            settings.min_dte,
    }


@router.post("")
def update_setting(payload: ConfigUpdate):
    allowed_keys = {
        "trading_mode", "max_risk_per_trade", "max_daily_drawdown",
        "max_positions", "min_rr_ratio", "squareoff_time",
        "max_iv_rank", "min_dte", "option_stop_loss_pct",
    }
    if payload.key not in allowed_keys:
        raise HTTPException(status_code=400, detail=f"Key '{payload.key}' not configurable via API")

    sdb.set_config(payload.key, payload.value)

    if hasattr(settings, payload.key):
        try:
            typed = type(getattr(settings, payload.key))(payload.value)
            object.__setattr__(settings, payload.key, typed)
        except Exception:
            pass

    return {"status": "updated", "key": payload.key, "value": payload.value}


# ── Kite Authentication ───────────────────────────────────────────────────────

@router.get("/kite/login-url")
def kite_login_url():
    """Return the Kite login URL to redirect the user to."""
    return {"login_url": kite_client.get_login_url()}


@router.get("/kite/callback")
def kite_callback(request_token: str):
    """
    Kite redirects here after login with ?request_token=...
    Exchanges it for an access token and saves it.
    """
    try:
        token = kite_client.generate_session(request_token)
        return RedirectResponse(url=f"http://localhost:5173?kite_auth=success&token={token[:8]}...")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Kite auth failed: {e}")


@router.get("/kite/status")
def kite_status():
    """Check if Kite is authenticated."""
    authenticated = kite_client.is_authenticated()
    return {"authenticated": authenticated}
