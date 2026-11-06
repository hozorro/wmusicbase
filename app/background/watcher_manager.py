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

import asyncio, os, time
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
from app.services.lyric_index_service import LyricIndexService
from app.services.lyric_service import LyricService
from app.models.track import Track
from app.utils.metadata import read_metadata
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
        
        # watchdog may hand over bytes on some platforms, fsdecode keeps both cases sound
        if Path(os.fsdecode(event.src_path)).suffix.lower() in settings.MUSIC_FILE_EXTENSIONS:
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
        self.queue: asyncio.Queue[tuple[str, str]] | None = None
        self._is_running = False
        self._tasks = []
        # lyric fetching runs in its own thread, submit() never blocks the event loop
        self.lyric_service = LyricService(settings)

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
        queue = self.queue
        if queue is None:
            logger.error('debounce worker started without a queue')
            return
        while self.is_running:
            now = time.time()
            paths_to_process = []

            for path, info in list(self.debounce_dict.items()):
                if now - info['time'] >= self.debounce_delay:
                    paths_to_process.append((path, info['type']))
                    del self.debounce_dict[path]
            
            for path, event_type in paths_to_process:
                await queue.put((path, event_type))

            await asyncio.sleep(1.0)

    async def _enqueue_lyric(self, db, path: str, meta: ParsedMeta) -> None:
        '''
        keep the lyric table aligned with tracks, then queue a background fetch.
        the lyric (.lrc, same name as the audio file) is written next to the track
        by the lyric worker thread. never raises: a lyric problem must not break
        the file pipeline.
        '''
        relative = relative_path(path)
        try:
            # one pending row per track, so the incremental fetcher always sees it
            await LyricIndexService(db, settings).ensure_row_by_track_path(relative)
            await db.commit()
        except Exception as e:
            logger.error(f'❌Ensure lyric row failed: {relative}: {e}')

        title = (meta.title or '').strip()
        if not title:
            logger.debug(f'🎵No title tag, skip lyric fetch: {relative}')
            return
        try:
            # the worker runs in its own thread, post results back to this loop
            loop = asyncio.get_running_loop()
            self.lyric_service.on_result = lambda res: asyncio.run_coroutine_threadsafe(
                self._persist_lyric(res), loop)
            queued = self.lyric_service.submit({
                'path': str(Path(path)),
                'title': title,
                'artists': list(meta.artists or []),
                'album': (meta.album or '').strip(),
                'duration': float(meta.duration or 0),
            })
        except Exception as e:
            logger.error(f'❌Queue lyric fetch failed: {relative}: {e}')
            return
        if queued:
            logger.info(f'🎵Lyric fetch queued: {relative}')
        else:
            logger.debug(f'🎵Lyric fetch ignored, already pending: {relative}')

    async def _persist_lyric(self, result) -> None:
        '''write a finished lyric fetch result back to the lyric table'''
        try:
            async with AsyncSessionLocal() as db:
                await LyricIndexService(db, settings).apply_fetch_result(result)
                await db.commit()
        except Exception as e:
            logger.error(f'❌Persist lyric result failed: {result.path}: {e}')

    async def _consumer_worker(self):
        queue = self.queue
        if queue is None:
            logger.error('consumer worker started without a queue')
            return

        async def handle_deletion(db, path):
            stmt = (
                update(Track)
                .where(Track.path == path)
                .values(is_deleted=True, deleted_at=datetime.now(timezone.utc))
            )
            await db.execute(stmt)
            await db.commit()

        async with AsyncSessionLocal() as db:
            processor = MusicFileProcessor(Path(self.root_path), db)
            artwork_service = ArtworkService(db, settings)

            while self.is_running:
                try:
                    path, event_type = await asyncio.wait_for(queue.get(), timeout=2.0)

                    try:
                        if event_type == 'deleted':
                            await handle_deletion(db, path)
                            logger.info(f'✅File marked deleted: {relative_path(path)}')
                        else:
                            meta = read_metadata(path)
                            if not meta:
                                # unreadable or unsupported tags: skip this file, keep the worker alive
                                logger.warning(f'Skip file without metadata: {relative_path(path)}')
                                continue
                            parsed = ParsedMeta.model_validate({"path": path, **meta})
                            await processor.process_single_file(parsed, True)
                            # commit immediately to get the track id of new tracks
                            if processor.pending_tracks:
                                await processor.commit_pending_tracks()
                            # sync artworks: track is always regenerated, album/artist
                            # are generated only when the static file is missing
                            await artwork_service.sync_artworks_after_track_change(relative_path(path))
                            await db.commit()
                            logger.info(f'✅File processed: {relative_path(path)}')
                            # metadata is in the database now, fetch the lyric in the background
                            await self._enqueue_lyric(db, path, parsed)
                    except Exception as e:
                        logger.error(f'❌Error processing file: {relative_path(path)}: {str(e)}')
                    finally:
                        queue.task_done()
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

        # lyric worker is a daemon thread, join it so no fetch outlives the watcher
        try:
            self.lyric_service.stop(timeout=2)
        except Exception as e:
            logger.warning(f'🛑Stop lyric service failed: {e}')

        logger.info("🛑Watcher stopped")
        system_state.is_watcher_running = False
        return True, "Watcher stopped"
        
    def is_running(self) -> bool:
        return self._is_running
    
watcher = WatcherManager(str(settings.MUSIC_LIBRARY_PATH))