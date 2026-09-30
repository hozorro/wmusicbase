# -*- encoding: utf-8 -*-
'''
@File      :   watcher_manager.py
@Time      :   2026/03/10 21:35:53
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   watcher manager
'''


# If use and triggle watcher in the fastapi background, 
# use this module and enable trigger in the frontend.
#
# If use watcher in separated process, 
# use supervisor to manage watcher with the watcher.py module,
# and disable trigger in the frontend.

import asyncio, time
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import update
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from app.core.logger import logger
from app.core.config import settings
from app.core.state import system_state
from app.core.db import AsyncSessionLocal
from app.services.processor import MusicFileProcessor
from app.services.artwork_service import ArtworkService
from app.models.track import Track
from app.utils.metadata import parse_metadata, easy_metadata
from app.schemas.filething import ParsedMeta

def relative_path(file_path: str | Path) -> str:
    '''get relative path from absolute path'''
    return str(Path(file_path).relative_to(settings.MUSIC_LIBRARY_PATH))

class MusicLibraryHandler(FileSystemEventHandler):
    def __init__(self, loop, callback):
        self.loop = loop
        self.callback = callback

    def on_any_event(self, event):
        if event.is_directory:
            return
        
        if Path(event.src_path).suffix.lower() in settings.MUSIC_FILE_EXTENSIONS:
            self.loop.call_soon_threadsafe(
                self.callback,
                event.src_path,
                event.event_type
            )

class WatcherManager:
    def __init__(self, root_path: str, debounce_delay: float = 3.0):
        self.root_path = root_path
        self.debounce_delay = debounce_delay
        self.debounce_dict = {} # {path: {'time': float, 'type': str}}
        self.observer = None
        self.queue = None
        self._is_running = False
        self._tasks = []

    def _is_file_ready(self, file_path: str) -> bool:
        '''check if file is ready to be processed'''
        try:
            with open(file_path, 'rb') as f:
                f.seek(0, 2)
                return f.tell() > 0
        except (OSError, IOError):
            return False

    def _add_to_debounce(self, path: str, event_type: str):
        '''
        record event. if it is continuous for the same file, update timestamp and reserve the last event type.
        '''
        if not self._is_file_ready(path): return
        self.debounce_dict[path] = {
            'time': time.time(),
            'type': event_type
        }

    async def _debounce_worker(self):
        while self.is_running:
            now = time.time()
            paths_to_process = []

            for path, info in list(self.debounce_dict.items()):
                if now - info['time'] >= self.debounce_delay:
                    paths_to_process.append((path, info['type']))
                    del self.debounce_dict[path]
            
            for path, event_type in paths_to_process:
                await self.queue.put((path, event_type))

            await asyncio.sleep(1.0)

    async def _consumer_worker(self):
        
        async def handle_deletion(db, path):
            stmt = (
                update(Track)
                .where(Track.path == path)
                .values(is_deleted=True, deleted_at=datetime.now(timezone.utc))
            )
            await db.execute(stmt)
            await db.commit()

        async with AsyncSessionLocal() as db:
            processor = MusicFileProcessor(self.root_path, db)
            artwork_service = ArtworkService(db, settings)

            while self.is_running:
                try:
                    path, event_type = await asyncio.wait_for(self.queue.get(), timeout=2.0)

                    try:
                        if event_type == 'deleted':
                            await handle_deletion(db, path)
                            logger.info(f'✅File marked deleted: {relative_path(path)}')
                        else:
                            if Path(path).suffix.lower() == ".mp3":
                                meta = parse_metadata(path)
                            else:
                                meta = easy_metadata(path)
                            await processor.process_single_file(ParsedMeta.model_validate({"path": path, **meta}), True)
                            # commit immediately to get the track id of new tracks
                            if processor.pending_tracks:
                                await processor.commit_pending_tracks()
                            # sync artworks: track is always regenerated, album/artist
                            # are generated only when the static file is missing
                            await artwork_service.sync_artworks_after_track_change(relative_path(path))
                            await db.commit()
                            logger.info(f'✅File processed: {relative_path(path)}')
                    except Exception as e:
                        logger.error(f'❌Error processing file: {relative_path(path)}: {str(e)}')
                    finally:
                        self.queue.task_done()
                except asyncio.TimeoutError:
                    if processor.pending_tracks:
                        await processor.commit_pending_tracks()

    def start(self) -> tuple[bool, str]:
        if self._is_running:
            return False, "Watcher is already running"
        self._is_running = True
        self.queue = asyncio.Queue()
        self.debounce_dict.clear()

        loop = asyncio.get_running_loop()

        event_handler = MusicLibraryHandler(loop, self._add_to_debounce)
        self.observer = Observer()
        self.observer.schedule(event_handler, self.root_path, recursive=True)
        self.observer.start()

        t1 = asyncio.create_task(self._debounce_worker())
        t2 = asyncio.create_task(self._consumer_worker())
        self._tasks = [t1, t2]

        logger.info("🚀Watcher started")
        system_state.is_watcher_running = True
        return True, "Watcher started"
        
    def stop(self) -> tuple[bool, str]:
        if not self._is_running: 
            return False, "Watcher is not running"
        
        self._is_running = False

        if self.observer: 
            self.observer.stop()
            self.observer.join()
            self.observer = None

        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        logger.info("🛑Watcher stopped")
        system_state.is_watcher_running = False
        return True, "Watcher stopped"
        
    def is_running(self) -> bool:
        return self._is_running
    
watcher = WatcherManager(str(settings.MUSIC_LIBRARY_PATH))