"""
Trading Scheduler — Index Options Buy-Side System
===================================================

Every scan cycle (9:15–15:20, every 5 min) runs a 3-stage gate:

  STAGE 1 — Hard Filters (pre_filter.py)
    VIX, IV rank, DTE, max-pain proximity, circuit breaker.

  STAGE 2 — ML Models (ml/inference.py)
    Direction (XGBoost 5-class) + Regime (RandomForest 7-class) +
    Timing (GradientBoosting binary, 1-min candles).

  STAGE 3 — LLM Signal (ai/signal_generator.py)
    GPT produces BUY_CE / BUY_PE / SKIP with premium targets.

Scheduled jobs (IST):
  09:00  pre_market_job
  09:15–15:20  trading_loop_job  (every 5 min)
  15:20  market_close_job
  Sunday 22:00  weekly_retrain_job
"""

import asyncio
from datetime import date

import pandas as pd
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from backend.config import settings
from backend.database import supabase_db as sdb

from backend.ai.day_classifier import classify_day
from backend.ai.sentiment_engine import build_market_context
from backend.ai.signal_generator import generate_signal

from backend.core.market_data import get_index_candles, get_index_ltp, INDEX_INSTRUMENTS
from backend.core.pre_filter import (
    session_gate, iv_gate, dte_gate, max_pain_gate, get_vix_context,
)

from backend.ml.inference import (
    load_models, get_direction, get_regime, get_entry_timing, models_ready,
)
from backend.ml.features import compute_features

from backend.trading.order_manager import process_signal
from backend.trading import paper_engine, live_engine
from backend.risk import risk_manager as rm
from backend.risk.circuit_breaker import is_triggered

from backend.utils.market_hours import is_market_open
from backend.utils.logger import get_logger

logger = get_logger(__name__)
IST = pytz.timezone("Asia/Kolkata")

_scheduler: AsyncIOScheduler | None = None
_ws_broadcast = None
_today_classification: dict = {}
_today_ml_direction: dict = {}


def set_ws_broadcaster(fn):
    global _ws_broadcast
    _ws_broadcast = fn


async def _broadcast(event: str, data: dict):
    if _ws_broadcast:
        await _ws_broadcast({"event": event, **data})


# ── Pre-Market (9:00 AM) ─────────────────────────────────────────────────────

async def run_pre_market():
    global _today_classification, _today_ml_direction
    logger.info("=== PRE-MARKET ===")

    # Stage 1: basic session check
    ok, reason = session_gate()
    if not ok and reason not in ("bot_not_running", "market_closed"):
        logger.warning(f"Pre-market blocked: {reason}")
        await _broadcast("session_blocked", {"reason": reason})
        return

    # Stage 2: ML direction for today
    ml_direction = {"direction": "FLAT", "trade_side": None, "is_strong": False}
    if models_ready():
        try:
            df_daily = get_index_candles("NIFTY", "day", days=365 * 5 + 30)
            if df_daily is not None and len(df_daily) >= 30:
                ml_direction = get_direction(df_daily)
                logger.info(
                    f"ML Direction: {ml_direction['direction']} "
                    f"bull={ml_direction.get('bull_prob', 0):.2f} "
                    f"bear={ml_direction.get('bear_prob', 0):.2f}"
                )
        except Exception as e:
            logger.warning(f"ML direction failed: {e}")

    _today_ml_direction = ml_direction

    # Stage 3: Full market context + Claude day classification
    try:
        ctx = build_market_context("NIFTY")
        vix_ctx = get_vix_context()
        ctx.update(vix_ctx)
        ctx["ml_direction"]  = ml_direction["direction"]
        ctx["ml_trade_side"] = ml_direction.get("trade_side")
        ctx["ml_is_strong"]  = ml_direction.get("is_strong", False)

        result = classify_day(ctx)
        _today_classification = result

        rm.set_risk_multiplier(result.get("risk_multiplier", 1.0))

        # Persist to Supabase
        existing = sdb.get_today_classification()
        if not existing:
            sdb.upsert_day_classification({
                "date":                 date.today().isoformat(),
                "score":                result["score"],
                "buy_side_score":       result.get("buy_side_score"),
                "classification":       result["classification"],
                "vix":                  ctx.get("vix"),
                "iv_rank":              ctx.get("iv_rank"),
                "premium_environment":  ctx.get("premium_environment"),
                "fii_net":              ctx.get("fii_net"),
                "fii_fut_ls_ratio":     ctx.get("fii_fut_ls_ratio"),
                "dii_net":              ctx.get("dii_net"),
                "pcr":                  ctx.get("put_call_ratio"),
                "nifty_gap":            ctx.get("nifty_gap_pct"),
                "global_sentiment":     ctx.get("global_sentiment"),
                "ml_direction":         ml_direction["direction"],
                "ml_regime":            None,
                "reasons_json":         result.get("key_reasons", []),
                "market_context_json":  ctx,
            })

        await _broadcast("day_classification", {
            "classification": result["classification"],
            "score":          result["score"],
            "buy_side_score": result.get("buy_side_score"),
            "ml_direction":   ml_direction["direction"],
            "trade_side":     ml_direction.get("trade_side"),
            "key_reasons":    result.get("key_reasons", []),
            "vix":            ctx.get("vix"),
            "iv_rank":        ctx.get("iv_rank"),
            "premium_env":    ctx.get("premium_environment"),
        })
        logger.info(
            f"Day classified: {result['classification']} score={result['score']} "
            f"buy_score={result.get('buy_side_score')} ML={ml_direction['direction']}"
        )

    except Exception as e:
        logger.error(f"Pre-market error: {e}", exc_info=True)


# ── Trading Loop (9:15–15:20, every 5 min) ──────────────────────────────────

async def run_trading_loop():
    if not is_market_open():
        return

    ok, reason = session_gate()
    if not ok:
        if reason != "bot_not_running":
            logger.info(f"Trading loop blocked: {reason}")
        return

    day_class = _today_classification or {
        "classification": "NEUTRAL", "score": 5,
        "buy_side_score": 5, "aggressiveness": "MEDIUM",
    }

    if day_class.get("classification") == "BAD" and day_class.get("score", 5) < 3:
        logger.info("Skipping — BAD day classification")
        return

    logger.info("=== TRADING LOOP ===")

    try:
        # Update open positions to market
        if settings.trading_mode == "paper":
            pos_summary = paper_engine.update_positions()
        else:
            live_engine.sync_live_positions()
            pos_summary = {"open": len(sdb.get_positions(mode="live"))}

        risk_metrics = rm.get_risk_metrics()
        await _broadcast("risk_update", risk_metrics)

        if is_triggered():
            return

        # Scan each index (NIFTY, BANKNIFTY)
        for index in settings.index_universe:
            if is_triggered():
                break

            # ── Stage 1: Hard gates ──────────────────────────────
            # IV rank gate
            mkt_ctx = _today_classification.get("_raw_ctx", {})
            iv_ok, iv_reason = iv_gate(mkt_ctx.get("iv_rank"))
            if not iv_ok:
                logger.info(f"[{index}] IV gate failed: {iv_reason}")
                continue

            # DTE gate
            dte_ok, dte_reason = dte_gate(index)
            if not dte_ok:
                logger.info(f"[{index}] DTE gate failed: {dte_reason}")
                continue

            # Max pain gate
            spot  = get_index_ltp(index)
            chain = mkt_ctx.get("options_chain", {})
            if spot and chain.get("max_pain"):
                mp_ok, mp_reason = max_pain_gate(spot, chain["max_pain"], "CE")
                if not mp_ok:
                    logger.info(f"[{index}] Max pain gate failed: {mp_reason}")

            # ── Stage 2: ML models ───────────────────────────────
            df_5m = get_index_candles(index, "5minute", days=30)
            df_1m = get_index_candles(index, "minute", days=5)

            if df_5m is None or len(df_5m) < 20:
                logger.warning(f"[{index}] Insufficient 5m data")
                continue

            regime_result = get_regime(df_5m)
            regime = regime_result["regime"]

            if not regime_result["is_tradeable"]:
                logger.info(f"[{index} S2 skip] Regime={regime} (not tradeable)")
                continue

            # Timing model (1-min) — only enter on high-confidence bars
            if df_1m is not None and len(df_1m) >= 15 and models_ready():
                timing = get_entry_timing(df_1m)
                if timing["action"] != "ENTER":
                    logger.debug(f"[{index}] Timing WAIT (p={timing['probability']:.2f})")
                    continue

            # ── Stage 3: LLM signal ──────────────────────────────
            enriched = {
                **day_class,
                "regime":            regime,
                "regime_strategy":   regime_result.get("strategy", "selective"),
                "regime_size_mult":  regime_result.get("size_multiplier", 1.0),
                "ml_direction":      _today_ml_direction.get("direction", "FLAT"),
                "ml_trade_side":     _today_ml_direction.get("trade_side"),
            }

            portfolio_state = {
                "open_positions":        risk_metrics["open_positions"],
                "max_positions":         settings.max_positions,
                "risk_budget_remaining": (
                    rm.get_risk_state().portfolio_value * settings.max_daily_drawdown / 100
                    + risk_metrics["daily_pnl"]
                ),
                "portfolio_value":       risk_metrics["portfolio_value"],
                "daily_pnl":             risk_metrics["daily_pnl"],
            }

            signal = await asyncio.get_event_loop().run_in_executor(
                None, lambda: generate_signal(index, enriched, portfolio_state)
            )

            if signal.get("signal") not in ("BUY_CE", "BUY_PE"):
                logger.info(f"[{index}] Signal=SKIP: {signal.get('reasoning', '')[:80]}")
                continue

            # Persist signal
            saved_signal = sdb.create_signal({
                "symbol":               signal.get("tradingsymbol", index),
                "index_name":           index,
                "signal":               signal["signal"],
                "option_type":          signal.get("option_type"),
                "strike":               signal.get("strike"),
                "expiry":               signal.get("expiry"),
                "lots":                 signal.get("lots"),
                "lot_size":             signal.get("lot_size"),
                "confidence":           signal.get("confidence", 5),
                "entry":                signal.get("entry_premium"),
                "target":               signal.get("target_premium"),
                "stop_loss":            signal.get("stop_premium"),
                "max_loss":             signal.get("max_loss"),
                "reasoning":            signal.get("reasoning"),
                "market_context_json":  enriched,
            })

            # Execute
            exec_result = process_signal({**signal, "signal_id": saved_signal.get("id")})

            if exec_result.get("executed"):
                sdb.mark_signal_executed(saved_signal["id"])

            await _broadcast("signal", {
                "index":       index,
                "signal":      signal["signal"],
                "tradingsymbol": signal.get("tradingsymbol"),
                "confidence":  signal.get("confidence"),
                "entry":       signal.get("entry_premium"),
                "target":      signal.get("target_premium"),
                "stop_loss":   signal.get("stop_premium"),
                "reasoning":   signal.get("reasoning"),
                "regime":      regime,
                "execution":   exec_result,
            })

            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Trading loop error: {e}", exc_info=True)


# ── Market Close (15:20) ─────────────────────────────────────────────────────

async def run_market_close():
    logger.info("=== MARKET CLOSE ===")
    try:
        if settings.trading_mode == "paper":
            pnl = paper_engine.squareoff_all()
        else:
            pnl = live_engine.squareoff_all()

        today_trades = sdb.get_trades(mode=settings.trading_mode, status="closed", limit=500)
        wins = [t for t in today_trades if (t.get("pnl") or 0) > 0]
        win_rate = round(len(wins) / len(today_trades) * 100 if today_trades else 0, 1)

        sdb.create_pnl_snapshot({
            "date":           date.today().isoformat(),
            "mode":           settings.trading_mode,
            "realized_pnl":   round(sum((t.get("pnl") or 0) for t in today_trades), 2),
            "unrealized_pnl": 0.0,
            "total_trades":   len(today_trades),
            "winning_trades": len(wins),
            "losing_trades":  len(today_trades) - len(wins),
            "win_rate":       win_rate,
            "portfolio_value": rm.get_risk_state().portfolio_value,
        })

        await _broadcast("eod_summary", {
            "pnl":          pnl,
            "total_trades": len(today_trades),
            "win_rate":     win_rate,
        })
        logger.info(f"EOD complete. P&L: ₹{pnl:+.2f} | trades={len(today_trades)} WR={win_rate}%")

    except Exception as e:
        logger.error(f"Market close error: {e}", exc_info=True)


# ── Weekly Retrain (Sunday 22:00) ────────────────────────────────────────────

async def run_weekly_retrain():
    logger.info("=== WEEKLY RETRAIN ===")
    try:
        from backend.ml.train import run as ml_train
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: ml_train(skip_fetch=False, force_fetch=False, model="all")
        )
        load_models()
        logger.info("Weekly retrain complete")
    except Exception as e:
        logger.error(f"Weekly retrain failed: {e}")


# ── Scheduler Lifecycle ──────────────────────────────────────────────────────

def start_scheduler():
    global _scheduler
    load_models()

    _scheduler = AsyncIOScheduler(timezone=IST)
    _scheduler.add_job(
        run_pre_market, CronTrigger(hour=9, minute=0, timezone=IST),
        id="pre_market", replace_existing=True,
    )
    _scheduler.add_job(
        run_trading_loop, CronTrigger(minute="*/5", hour="9-15", timezone=IST),
        id="trading_loop", replace_existing=True,
    )
    _scheduler.add_job(
        run_market_close, CronTrigger(hour=15, minute=20, timezone=IST),
        id="market_close", replace_existing=True,
    )
    _scheduler.add_job(
        run_weekly_retrain, CronTrigger(day_of_week="sun", hour=22, minute=0, timezone=IST),
        id="weekly_retrain", replace_existing=True,
    )
    _scheduler.start()
    logger.info("Scheduler started | ML=" + ("ACTIVE" if models_ready() else "FALLBACK"))
    return _scheduler


def stop_scheduler():
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
