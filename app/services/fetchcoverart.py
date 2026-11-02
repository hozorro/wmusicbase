# -*- encoding: utf-8 -*-
'''
@File      :   fetchcoverart.py
@Time      :   2026/02/18 13:19:13
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   fetch coverart from 3rd-party api
'''


import requests
from collections.abc import MutableMapping
from typing import cast
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from cachetools import TTLCache
from threading import Lock, Event
from PIL import Image
from io import BytesIO
from app.core.config import settings
from app.core.logger import logger

# safety net only: a single fetch is bounded by the (3, 8) requests timeouts, waiters
# should practically always be woken up by the owner thread
_PENDING_WAIT_SECONDS = 15.0

# typed cache: fetches that return None(no cover found) are cached on purpose, so the
# value type must stay Optional. cast is used because TTLCache is not generic at
# runtime(cachetools 5.x).
cover_cache: MutableMapping[str, bytes | None] = cast(
    MutableMapping[str, bytes | None],
    TTLCache(maxsize=settings.CACHE_MAX, ttl=settings.CACHE_EXPIRE)
)
# guards cover_cache and _pending_events only, never held during network io
debounce_lock = Lock()
# release_id -> event, set by the owner thread once the result is published
_pending_events: dict[str, Event] = {}

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

def _fetch_and_cache(release_id: str) -> bytes | None:
    '''fetch cover art and publish the result into the cache'''
    cover_data = fetch_cover_art(release_id)
    with debounce_lock:
        cover_cache[release_id] = cover_data
    return cover_data

def get_cover_art(release_id: str) -> bytes | None:
    '''get cover art, concurrent requests for one release share a single fetch'''
    with debounce_lock:
        if release_id in cover_cache:
            return cover_cache[release_id]
        event = _pending_events.get(release_id)
        is_owner = event is None
        if is_owner:
            event = Event()
            _pending_events[release_id] = event

    if not is_owner:
        # another thread owns the fetch: wait for it outside the lock, so the owner can
        # still publish its result while we are waiting
        if event.wait(timeout=_PENDING_WAIT_SECONDS):
            with debounce_lock:
                return cover_cache.get(release_id)
        logger.warning(f'In-flight cover art fetch timed out, fetching directly: {release_id}')

    try:
        return _fetch_and_cache(release_id)
    finally:
        # only the owner unregisters its own event and wakes the waiters up
        if is_owner:
            with debounce_lock:
                _pending_events.pop(release_id, None)
            event.set()

def clear_cached_cover(release_id: str):
    with debounce_lock:
        event = _pending_events.pop(release_id, None)
        cover_cache.pop(release_id, None)
    if event is not None:
        # release the threads waiting for this release, they will re-check the cache
        event.set()

def clear_cover_cache():
    with debounce_lock:
        events = list(_pending_events.values())
        _pending_events.clear()
        cover_cache.clear()
    for event in events:
        event.set()