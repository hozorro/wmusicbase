# -*- encoding: utf-8 -*-
'''
@File      :   sync.py
@Time      :   2025/10/20 12:15:29
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   file event handler
'''


import asyncio
from app.core.db import AsyncSessionLocal
from app.core.config import settings
from app.services.scanner import get_track_by_path
from app.services.processor import MusicFileProcessor
from app.services.artwork import invalidate_artwork_cache
from app.utils.metadata import extract_cover_art_hash
from pathlib import Path

async def _handle_event_async(event_type: str, file_path: str):
    async with AsyncSessionLocal() as db:
        if event_type == 'deleted':
            # 标记Track为软删除
            track = await get_track_by_path(db, file_path)
            if track:
                track.is_deleted = True
                from datetime import datetime
                track.deleted_at = datetime.now()
                await db.commit()
        else: # created or modified
            new_cover_art_hash = extract_cover_art_hash(file_path)
            track = await get_track_by_path(db, file_path)
            if track and track.cover_art_hash != new_cover_art_hash:
                invalidate_artwork_cache(track.id)
            processor = MusicFileProcessor(db)
            await processor.process_single_file(Path(file_path), Path(settings.MUSIC_LIBRARY_PATH))
            db.commit()

def handle_file_evant(event_type: str, file_path: str):
    '''在同步上下文中调用异步处理函数'''
    asyncio.run(_handle_event_async(event_type, file_path))