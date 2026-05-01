from fastapi import APIRouter
from backend.database import supabase_db as sdb
from backend.risk.risk_manager import get_risk_metrics
from backend.config import settings

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def get_dashboard():
    day_class = sdb.get_today_classification()
    risk = get_risk_metrics()
    positions = sdb.get_positions(mode=settings.trading_mode)
    today_trades = sdb.get_trades(mode=settings.trading_mode, status="closed", limit=200)
    wins = [t for t in today_trades if (t.get("pnl") or 0) > 0]

    return {
        "trading_mode": settings.trading_mode,
        "day_classification": {
            "score":          day_class.get("score") if day_class else None,
            "buy_side_score": day_class.get("buy_side_score") if day_class else None,
            "classification": (day_class.get("classification") or "PENDING") if day_class else "PENDING",
            "key_reasons":    day_class.get("reasons_json", []) if day_class else [],
            "vix":            day_class.get("vix") if day_class else None,
            "fii_net":        day_class.get("fii_net") if day_class else None,
            "ml_direction":   day_class.get("ml_direction") if day_class else None,
            "ml_regime":      day_class.get("ml_regime") if day_class else None,
            "premium_env":    day_class.get("premium_environment") if day_class else None,
        },
        "risk": risk,
        "positions": [
            {
                "symbol":        p["symbol"],
                "side":          p["side"],
                "qty":           p["quantity"],
                "entry":         p["entry_price"],
                "current":       p.get("current_price"),
                "unrealized_pnl": p.get("unrealized_pnl", 0),
                "stop_loss":     p.get("stop_loss"),
                "target":        p.get("target"),
            }
            for p in positions
        ],
        "today_stats": {
            "total_trades":   len(today_trades),
            "winning_trades": len(wins),
            "win_rate":       round(len(wins) / len(today_trades) * 100 if today_trades else 0, 1),
            "realized_pnl":   round(sum((t.get("pnl") or 0) for t in today_trades), 2),
        },
    }
