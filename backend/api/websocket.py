import asyncio
import json
from fastapi import WebSocket, WebSocketDisconnect
from backend.utils.logger import get_logger

logger = get_logger(__name__)

_connections: set[WebSocket] = set()


async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connections.add(websocket)
    logger.info(f"WebSocket connected: {websocket.client}")
    try:
        while True:
            # Keep alive — receive pings from client
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            if data == "ping":
                await websocket.send_text("pong")
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        _connections.discard(websocket)
        logger.info(f"WebSocket disconnected: {websocket.client}")


async def broadcast(message: dict):
    """Broadcast a JSON message to all connected WebSocket clients."""
    if not _connections:
        return
    text = json.dumps(message)
    dead = set()
    for ws in list(_connections):
        try:
            await ws.send_text(text)
        except Exception:
            dead.add(ws)
    _connections.difference_update(dead)


def get_connection_count() -> int:
    return len(_connections)
