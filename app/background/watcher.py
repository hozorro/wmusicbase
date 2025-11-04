# -*- encoding: utf-8 -*-
'''
@File      :   watcher.py
@Time      :   2025/10/20 12:14:08
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   musiclib directory watcher
'''


import threading
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pathlib import Path
from app.core.config import settings
from app.core.state import system_state
from app.services.sync import handle_file_evant
import logging

logger = logging.getLogger(__name__)

observer = None
watch_thread = None

class MusicLibraryHandler(FileSystemEventHandler):

    def _is_music_file(self, path):
        return Path(path).suffix.lower() in settings.MUSIC_FILE_EXTENSIONS
    def on_created(self, event):
        if not event.is_directory and self._is_music_file(event.src_path):
            logger.info(f'File created: {event.src_path}')
            handle_file_evant('created', event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._is_music_file(event.src_path):
            # 防抖：避免编辑器保持多次触发
            time.sleep(1)
            logger.info(f'File modified: {event.src_path}')
            handle_file_evant('modified', event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and self._is_music_file(event.src_path):
            logger.info(f'File deleted: {event.src_path}')
            handle_file_evant('deleted', event.src_path)

def _run_watcher():
    global observer
    event_handler = MusicLibraryHandler()
    observer = Observer()
    observer.schedule(event_handler, settings.MUSIC_LIBRARY_PATH, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

def start_watcher():
    global watch_thread
    if watch_thread is None:
        watch_thread = threading.Thread(target=_run_watcher, daemon=True)
        watch_thread.start()
        system_state.is_watcher_running = True

def stop_watcher():
    global observer, watch_thread
    if observer:
        observer.stop()
        observer.join()
    if watch_thread:
        watch_thread.join()
    observer = None
    watch_thread = None
    system_state.is_watcher_running = False
