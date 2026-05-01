"""
Database bootstrap — uses Supabase REST via supabase-py.
Tables must be created manually in Supabase SQL Editor (see supabase_schema.sql).
"""

from backend.database.supabase_db import get_client
from backend.utils.logger import get_logger

logger = get_logger(__name__)


def init_db() -> None:
    """Verify Supabase connection on startup."""
    try:
        client = get_client()
        client.table("bot_config").select("id").limit(1).execute()
        logger.info("Supabase connected OK")
    except Exception as e:
        logger.error(f"Supabase connection failed: {e}")
        raise
