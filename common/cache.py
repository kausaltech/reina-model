import pandas as pd
from flask_caching import Cache


_cache_backend = None


def _init_local_cache():
    from common import settings
    global _cache_backend

    if settings.CACHE_TYPE == 'simple':
        from flask_caching.backends.simple import SimpleCache

        _cache_backend = SimpleCache()
    elif settings.CACHE_TYPE == 'redis':
        from redis import from_url as redis_from_url
        from flask_caching.backends.rediscache import RedisCache

        _cache_backend = RedisCache(
            key_prefix=settings.CACHE_KEY_PREFIX,
            host=redis_from_url(settings.CACHE_REDIS_URL)
        )


def get(key):
    if _cache_backend is None:
        _init_local_cache()

    return _cache_backend.get(key)


def set(key, val, timeout=None):
    if _cache_backend is None:
        _init_local_cache()

    _cache_backend.set(key, val)


def init_app(app):
    global memoize, get, set

    _cache = Cache()
    _cache.init_app(app)

    memoize = _cache.memoize
    get = _cache.get
    set = _cache.set
