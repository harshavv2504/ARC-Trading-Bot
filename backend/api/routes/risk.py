from fastapi import APIRouter
from backend.risk.risk_manager import get_risk_metrics, reset_circuit_breaker
from backend.risk.circuit_breaker import trigger_emergency_stop

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("")
def get_risk():
    return get_risk_metrics()


@router.post("/reset-circuit-breaker")
def reset_cb():
    reset_circuit_breaker()
    return {"status": "circuit breaker reset"}
