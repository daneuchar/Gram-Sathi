from cachetools import TTLCache

# Shared in-memory caches
# Prototype: no Redis needed. Production swap: replace with async Redis client.
# Interface (cache_get / cache_set / is_rate_limited) stays identical on swap.

_api_cache = TTLCache(maxsize=1000, ttl=1800)       # 30-min default (mandi prices)
_rate_limit_cache = TTLCache(maxsize=500, ttl=60)   # 60-sec (duplicate callback guard)


def cache_get(key: str):
    return _api_cache.get(key)


def cache_set(key: str, value: str, ttl_seconds: int = 1800):
    # cachetools TTLCache uses constructor TTL; we store with default.
    # For varied TTLs in production, use a Redis client with per-key TTL.
    _api_cache[key] = value


def is_rate_limited(key: str) -> bool:
    """Return True if this key was seen within the last 60 seconds."""
    if key in _rate_limit_cache:
        return True
    _rate_limit_cache[key] = 1
    return False
