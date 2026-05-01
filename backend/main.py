from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.database.db import init_db
from backend.risk.risk_manager import initialize as init_risk
from backend.risk.circuit_breaker import register_emergency_callback
from backend.core.scheduler import start_scheduler, stop_scheduler, set_ws_broadcaster
from backend.api.websocket import websocket_endpoint, broadcast
from backend.api.routes import dashboard, trades, positions, signals, risk, settings as settings_route, bot
from backend.trading import paper_engine, live_engine
from backend.utils.logger import get_logger

logger = get_logger(__name__)


async def _emergency_close_all(reason: str):
    if settings.trading_mode == "paper":
        paper_engine.squareoff_all()
    else:
        live_engine.squareoff_all()
    await broadcast({"event": "emergency_stop", "reason": reason})


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("=== ARC Trading Bot Starting ===")
    init_db()
    init_risk(settings.portfolio_value)
    register_emergency_callback(_emergency_close_all)
    set_ws_broadcaster(broadcast)
    start_scheduler()
    logger.info(f"Mode: {settings.trading_mode.upper()} | Portfolio: ₹{settings.portfolio_value:,.0f}")
    yield
    # Shutdown
    stop_scheduler()
    logger.info("=== ARC Trading Bot Stopped ===")


app = FastAPI(
    title="ARC Trading Bot",
    description="AI-powered NSE India trading bot with paper and live trading",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(dashboard.router)
app.include_router(trades.router)
app.include_router(positions.router)
app.include_router(signals.router)
app.include_router(risk.router)
app.include_router(settings_route.router)
app.include_router(bot.router)


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket_endpoint(websocket)


@app.get("/health")
def health():
    return {"status": "ok", "mode": settings.trading_mode}
