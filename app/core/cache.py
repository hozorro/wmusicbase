# -*- encoding: utf-8 -*-
'''
@File      :   cache.py
@Time      :   2025/12/10 10:11:02
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   cache management
'''


from cachetools import TTLCache, LRUCache

ttl_cache = TTLCache(maxsize=100, ttl=60 * 10)  # 10 minutes
lru_cache = LRUCache(maxsize=100)