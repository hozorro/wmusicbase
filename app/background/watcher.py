# -*- encoding: utf-8 -*-
'''
@File      :   watcher.py
@Time      :   2025/10/20 12:14:08
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   musiclib directory watcher
'''


# If use and triggle watcher in the fastapi background, 
# use the watcher_manager.py module and enable trigger in the frontend.
#
# If use watcher in separated process, 
# use supervisor to manage watcher with this module,
# and disable trigger in the frontend.

import time, asyncio, signal
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from app.core.db import AsyncSessionLocal
from app.core.config import settings
from app.core.logger import logger, init_logging
from app.services.processor import MusicFileProcessor
from app.services.artwork_service import ArtworkService
from app.services.lyric_index_service import LyricIndexService
from app.services.lyric_service import LyricService
from app.models.track import Track
from app.utils.metadata import easy_metadata, parse_metadata
from app.schemas.filething import ParsedMeta

init_logging()

def relative_path(file_path: str | Path) -> str:
    '''get relative path from absolute path'''
    return str(Path(file_path).relative_to(settings.MUSIC_LIBRARY_PATH))

class MusicLibraryHandler(FileSystemEventHandler):
    '''watchdog event handler(running in a separate thread)'''
    def __init__(self, loop: asyncio.AbstractEventLoop, add_to_debounce_cb):
        self.loop = loop    # asyncio main loop
        self.add_to_debounce = add_to_debounce_cb   # add to debounce callback

    def _add_event(self, event):
        if event.is_directory:
            return
        if Path(event.src_path).suffix.lower() in settings.MUSIC_FILE_EXTENSIONS:
            self.loop.call_soon_threadsafe(self.add_to_debounce, event.src_path, event.event_type)
    def on_created(self, event):
        self._add_event(event)
    
    def on_modified(self, event):
        self._add_event(event)

    def on_deleted(self, event):
        self._add_event(event)

class MusicLibraryWatcher:
    def __init__(self, root_path: str, debounce_delay: float = 2.0):
        self.root_path = root_path
        self.queue = asyncio.Queue()

        self.debounce_dict = {} # {filepath: {'event_type': str, 'timestamp': float}}
        self.debounce_delay = debounce_delay
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

    def add_to_debounce(self, file_path: str, event_type: str):
        '''troggled by watchdog, executes in the main asyncio loop'''
        if not self._is_file_ready(file_path): return
        self.debounce_dict[file_path] = {'event_type': event_type, 'time': time.time()}
        logger.debug(f'Detected file {event_type}: {relative_path(file_path)}')
    
    async def debounce_worker(self):
        '''
        async debounce worker, check which files is 'silent down',
        executes in the main asyncio loop
        '''
        logger.info('Debounce worker started.')
        while True:
            now = time.time()
            to_process = []

            for path, event_data in list(self.debounce_dict.items()):
                if now - event_data['time'] > self.debounce_delay:
                    # keep the event payload, the path alone cannot rebuild it
                    to_process.append((path, event_data))
                    del self.debounce_dict[path]

            for path, event_data in to_process:
                await self.queue.put((path, event_data['event_type']))

            await asyncio.sleep(0.5)

    async def _enqueue_lyric(self, db, file_path: str, meta: ParsedMeta):
        '''
        keep the lyric table aligned with tracks, then queue a background fetch.
        the lyric (.lrc, same name as the audio file) is written next to the track
        by the lyric worker thread. never raises: a lyric problem must not break
        the file pipeline.
        '''
        relative = relative_path(file_path)
        try:
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
                'path': str(Path(file_path)),
                'title': title,
                'artists': list(meta.artists or []),
                'album': (meta.album or '').strip(),
                'duration': float(meta.duration or 0),
            })
        except Exception as e:
            logger.error(f'❌Queue lyric fetch failed: {relative}: {e}')
            return
        if queued:
            logger.info(f'🎵Lyric fetch queued: {relative_path(file_path)}')
        else:
            logger.debug(f'🎵Lyric fetch ignored, already pending: {relative_path(file_path)}')

    async def _persist_lyric(self, result) -> None:
        '''write a finished lyric fetch result back to the lyric table'''
        try:
            async with AsyncSessionLocal() as db:
                await LyricIndexService(db, settings).apply_fetch_result(result)
                await db.commit()
        except Exception as e:
            logger.error(f'❌Persist lyric result failed: {result.path}: {e}')

    async def consumer_worker(self):
        '''
        async consumer worker, handle file event,
        executes in the main asyncio loop
        '''
        async def _get_track_by_path(db: AsyncSession, file_path: str) -> Track | None:
            path = relative_path(file_path)
            result = await db.execute(select(Track).where(Track.path == path))
            return result.scalar_one_or_none()
        
        logger.info('Consumer worker started.')
        async with AsyncSessionLocal() as db:
            processor = MusicFileProcessor(Path(settings.MUSIC_LIBRARY_PATH), db)
            artwork_service = ArtworkService(db, settings)
            while True:
                try:
                    file_path, event_type = await asyncio.wait_for(self.queue.get(), timeout=5.0)
                    if event_type == 'deleted':
                        track = await _get_track_by_path(db, file_path)
                        if track:
                            track.is_deleted = True
                            db.add(track)
                            await db.commit()
                            logger.info(f'Deleted file: {relative_path(file_path)}')
                        else:
                            logger.warning(f'Track not found: {relative_path(file_path)}')
                    else:
                        try:
                            if Path(file_path).suffix.lower() == ".mp3":
                                meta = parse_metadata(file_path)
                            else:
                                meta = easy_metadata(file_path)
                            if not meta:
                                # unreadable or unsupported tags: skip this file, keep the queue alive
                                logger.warning(f'Skip file without metadata: {relative_path(file_path)}')
                                continue
                            parsed = ParsedMeta.model_validate({"path": file_path, **meta})
                            await processor.process_single_file(parsed, True)
                            # commit immediately to get the track id of new tracks
                            if len(processor.pending_tracks) > 0:
                                await processor.commit_pending_tracks()
                            # sync artworks: track is always regenerated, album/artist
                            # are generated only when the static file is missing
                            await artwork_service.sync_artworks_after_track_change(relative_path(file_path))
                            await db.commit()
                            logger.info(f'✅File processed: {relative_path(file_path)}')
                            # metadata is in the database now, fetch the lyric in the background
                            await self._enqueue_lyric(db, file_path, parsed)
                        except Exception as e:
                            logger.error(f'❌Commit pending tracks error: {str(e)}', exc_info=True)
                        finally:
                            self.queue.task_done()
                except asyncio.TimeoutError:
                    if len(processor.pending_tracks) > 0:
                        try:
                            await processor.commit_pending_tracks()
                        except Exception as e:
                            logger.error(f'❌Commit pending tracks error: {str(e)}', exc_info=True)
                    
    async def run(self):
        '''main loop'''
        loop = asyncio.get_running_loop()

        event_handler = MusicLibraryHandler(loop, self.add_to_debounce)
        observer = Observer()
        observer.schedule(event_handler, self.root_path, recursive=True)
        observer.start()
        logger.info('Watcher started.')

        try:
            debounce_task = asyncio.create_task(self.debounce_worker())
            consumer_task = asyncio.create_task(self.consumer_worker())
            await asyncio.gather(debounce_task, consumer_task)
        except asyncio.CancelledError:
            logger.info(f'Watcher stopped.')
        except Exception as e:
            logger.error(f'Watcher error: {e}')
        finally:
            observer.stop()
            observer.join()
            # lyric worker is a daemon thread, join it so no fetch outlives the watcher
            try:
                self.lyric_service.stop(timeout=2)
            except Exception as e:
                logger.warning(f'🛑Stop lyric service failed: {e}')

if __name__ == '__main__':
    watcher = MusicLibraryWatcher(str(settings.MUSIC_LIBRARY_PATH))

    # Handle SIGTERM from supervisor for graceful shutdown
    def _signal_handler(signum, frame):
        logger.info(f'Received signal {signum}, shutting down...')
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        asyncio.run(watcher.run())
    except KeyboardInterrupt:
        logger.info('Watcher stopped.')