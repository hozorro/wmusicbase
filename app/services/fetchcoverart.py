# -*- encoding: utf-8 -*-
'''
@File      :   fetchcoverart.py
@Time      :   2026/02/18 13:19:13
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   fetch coverart from 3rd-party api
'''


import requests, time
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from cachetools import TTLCache
from threading import Lock
from PIL import Image
from io import BytesIO
from app.core.config import settings
from app.core.logger import logger

cover_cache = TTLCache(maxsize=settings.CACHE_MAX, ttl=settings.CACHE_EXPIRE)
debounce_lock = Lock()
debounce_pending: dict[str, tuple[bool, bytes | None]] = {}

def get_requests_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3, 
        backoff_factor=0.5, 
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=['GET']
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({'User-Agent': 'WMusicBase/1.0 + https://github.com/WMusicBase/WMusicBase'})
    return session

def fetch_cover_art(release_id: str) -> bytes | None:
    session = get_requests_session()
    cover_data = None
    try:
        for path in settings.COVER_ART_PATH:
            cover_url = settings.COVER_ART_BASE_URL + path.format(release_id=release_id)
            response = session.get(cover_url, timeout=(3, 8), stream=True)
            response.raise_for_status()
            if not response.headers.get('Content-Type', '').startswith('image/'):
                continue
            with Image.open(BytesIO(response.content)) as img:
                img.thumbnail((512, 512), Image.Resampling.LANCZOS)
                img_byte_arr = BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=85)
                cover_data = img_byte_arr.getvalue()
            break
    except Exception as e:
        logger.error(f'Failed to fetch cover art for release {release_id}: {e}')
    return cover_data

def get_cover_art(release_id: str) -> bytes | None:
    if release_id in cover_cache:
        return cover_cache[release_id]
    
    with debounce_lock:
        if release_id in debounce_pending:
            pending, data = debounce_pending[release_id]
            wait_start = time.time()
            while pending and (time.time() - wait_start < 5):
                time.sleep(0.01)
                pending, data = debounce_pending[release_id]
            if data:
                cover_cache[release_id] = data
                del debounce_pending[release_id]
                return data
        debounce_pending[release_id] = (True, None)

    cover_data = fetch_cover_art(release_id)
    with debounce_lock:
        debounce_pending[release_id] = (True, cover_data)
        cover_cache[release_id] = cover_data
        time.sleep(0.1)
        if release_id in debounce_pending:
            del debounce_pending[release_id]

    return cover_data
def clear_cached_cover(release_id: str):
    with debounce_lock:
        debounce_pending.pop(release_id, None)
        cover_cache.pop(release_id, None)
def clear_cover_cache():
    with debounce_lock:
        debounce_pending.clear()
        cover_cache.clear()