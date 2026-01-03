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
from pathlib import Path
from app.core.db import AsyncSessionLocal
from app.core.deps import SettingsDep
from app.services.scanner import get_track_by_path
from app.services.processor import MusicFileProcessor
from app.services.artwork_service import ArtworkService
from app.utils.metadata import extract_cover_art_hash

async def _handle_event_async(event_type: str, file_path: str, settings: SettingsDep):
    async with AsyncSessionLocal() as db:
        if event_type == 'deleted':
            # mark track as soft deleted
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
                service = ArtworkService(db)
                service.invalidate_artwork_cache(track.id, 'track')
            processor = MusicFileProcessor(Path(settings.MUSIC_LIBRARY_PATH), db)
            await processor.process_single_file(Path(file_path))
            db.commit()

def handle_file_event(event_type: str, file_path: str):
    '''call an asynchronous processing function within a synchronous context'''
    asyncio.run(_handle_event_async(event_type, file_path))