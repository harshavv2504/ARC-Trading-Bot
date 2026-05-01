from fastapi import APIRouter
from backend.risk import risk_manager as rm
from backend.risk.circuit_breaker import trigger_emergency_stop
from backend.core.scheduler import run_pre_market, run_trading_loop, run_market_close
from backend.config import settings
from backend.utils.logger import get_logger
import asyncio

router = APIRouter(prefix="/api/bot", tags=["bot"])
logger = get_logger(__name__)


@router.post("/start")
async def start_bot():
    if rm.get_risk_state().circuit_breaker_triggered:
        return {"status": "error", "message": "Circuit breaker active — reset it first"}
    rm.get_risk_state().bot_running = True
    logger.info("Bot started by user")
    return {"status": "running", "mode": settings.trading_mode}


@router.post("/stop")
def stop_bot():
    rm.get_risk_state().bot_running = False
    logger.info("Bot stopped by user")
    return {"status": "stopped"}


@router.post("/emergency-stop")
async def emergency_stop():
    await trigger_emergency_stop("User triggered emergency stop")
    return {"status": "emergency_stop_triggered"}


@router.post("/run-pre-market")
async def manual_pre_market():
    """Manually trigger pre-market day classification."""
    await run_pre_market()
    return {"status": "pre_market_complete"}


@router.post("/run-trading-loop")
async def manual_trading_loop():
    """Manually trigger one trading loop cycle."""
    await run_trading_loop()
    return {"status": "trading_loop_complete"}


@router.get("/status")
def bot_status():
    from backend.ml.inference import models_ready
    from backend.ml.day_model import DayModel
    from backend.ml.regime_model import RegimeModel
    state = rm.get_risk_state()
    return {
        "running": state.bot_running,
        "mode": settings.trading_mode,
        "circuit_breaker": state.circuit_breaker_triggered,
        "open_positions": state.open_positions,
        "ml_models_ready": models_ready(),
        "day_model_exists": DayModel.exists(),
        "regime_model_exists": RegimeModel.exists(),
    }


@router.post("/train-models")
async def trigger_training(skip_fetch: bool = False):
    """Kick off ML model training in the background."""
    from backend.ml.train import run as ml_train
    from backend.ml.inference import load_models
    import asyncio

    async def _train():
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, lambda: ml_train(skip_fetch=skip_fetch, force_fetch=False, model="all")
        )
        load_models()

    asyncio.create_task(_train())
    return {
        "status": "training_started",
        "note": "Training runs in background (~10 min fetch + ~5 min train). Watch logs."
    }


@router.post("/kite-login")
def get_kite_login_url():
    from backend.core.kite_client import kite_client
    url = kite_client.get_login_url()
    return {"login_url": url}


@router.post("/kite-session")
def generate_kite_session(request_token: str):
    from backend.core.kite_client import kite_client
    try:
        token = kite_client.generate_session(request_token)
        return {"status": "authenticated", "access_token": token[:8] + "..."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
