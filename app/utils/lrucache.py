# -*- encoding: utf-8 -*-
'''
@File      :   lrucache.py
@Time      :   2025/12/08 15:35:52
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   extend functools.lru_cache with ttl(not use, insteaded by cachetools.ttlcache)
'''


import time, functools

def lru_cache_ttl(ttl=60, *lru_args, **lru_kwargs):
    """Decorator that extends functools.lru_cache with a time-to-live (TTL) feature."""
    def decorator(func):
        func = functools.lru_cache(*lru_args, **lru_kwargs)(func)
        func.delta = ttl
        func.expiration = time.monotonic() + func.delta

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if time.monotonic() > func.expiration:
                func.cache_clear()
                func.expiration = time.monotonic() + func.delta
            return func(*args, **kwargs)
            
        wrapper.cache_info = func.cache_info
        wrapper.cache_clear = func.cache_clear
        return wrapper
    return decorator