import time
from functools import wraps
from typing import Any, Callable


_cache: dict[str, tuple[Any, float]] = {}


def ttl_cache(ttl: int = 60):
    """Simple in-memory TTL cache decorator."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"{fn.__qualname__}:{args}:{kwargs}"
            now = time.time()
            if key in _cache:
                val, exp = _cache[key]
                if now < exp:
                    return val
            result = fn(*args, **kwargs)
            _cache[key] = (result, now + ttl)
            return result
        return wrapper
    return decorator


def invalidate_cache():
    _cache.clear()
