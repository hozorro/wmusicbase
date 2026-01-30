# -*- encoding: utf-8 -*-
'''
@File      :   scanner.py
@Time      :   2025/10/20 11:06:43
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   scanner
'''


import asyncio
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.logger import logger
from app.core.db import safe_async_transaction, AsyncSessionLocal
from app.core.config import settings
from app.core.state import system_state
from app.models import Track, Folder, SyncMeta
from app.services.processor import MusicFileProcessor
from app.services.sync import Syncer
from app.schemas.sysinfo import ScanFolder

# ========== global signals ==========
_scan_cancel_event = asyncio.Event()
_scan_lock = asyncio.Lock()
MAX_RETRIES = 3

# ========== control interface =======
async def get_scan_folder(db: AsyncSession) -> ScanFolder:
    result = await db.execute(select(Folder).where(Folder.parent_id == None))
    folder = result.scalar_one_or_none()
    if folder: 
        result_update = await db.execute(select(func.max(SyncMeta.last_update)).where(SyncMeta.user_id == None))
        folder_path = settings.MUSIC_LIBRARY_PATH / Path(folder.path)
        return ScanFolder(path=str(folder_path), created_at=folder.created_at, last_update=result_update.scalar_one_or_none())
    else:
        return None
def cancel_scan():
    '''cancel scan'''
    _scan_cancel_event.set()

def reset_scan_cancel():
    '''reset scan cancel signal'''
    _scan_cancel_event.clear()

async def get_track_by_path(db: AsyncSession, file_path: str) -> Track | None:
    '''lookup Track by absolute path(including soft deleted)'''
    result = await db.execute(select(Track).where(Track.path == file_path))
    return result.scalar_one_or_none()

# ========== 扫描逻辑 ==============
async def process_in_batches(files: list[Path], root_path: Path, batch_size: int = 20):
    '''process files in batches, commit to db one by one'''
    semaphore = asyncio.Semaphore(batch_size) # control concurrency

    async def process_file(file_path: Path):
        if _scan_cancel_event.is_set(): 
            return

        async with semaphore:
            if _scan_cancel_event.is_set(): 
                return False
            async with AsyncSessionLocal() as db:
                try:
                    processor = MusicFileProcessor(root_path, db)
                    system_state.scan_progress['current_file'] = str(file_path.relative_to(root_path))
                    result = await safe_async_transaction(db, processor.process_single_file, file_path)
                    await db.commit()
                    return result
                except Exception as e:
                    await db.rollback()
                    logger.error(f"❌fail to process {file_path} and rollback: {str(e)}", exc_info=True)
                    return False
        return False
        
    total = len(files)
    system_state.init_scan_state()
    system_state.scan_progress['total'] = total
    total_batch_count = (total + batch_size - 1) // batch_size
    total_error = 0
    total_success = 0
    for i in range(0, total, batch_size):
        batch = files[i:i+batch_size]
        # handle batches in parallel (control concurrency by semaphore)      
        results = await asyncio.gather(*[process_file(file_path) for file_path in batch], return_exceptions=True)
        success = sum([1 for result in results if not isinstance(result, Exception)])
        error = len(batch) - success
        total_error += error
        total_success += success
        cur_batch = i // batch_size + 1
        system_state.scan_progress['processed'] = i + len(results)
        system_state.scan_progress['success'] = total_success
        system_state.scan_progress['failed'] = total_error
        print(f"\r🔍Total: {total}; handled batches {cur_batch}/{total_batch_count}: success {success}/{len(batch)}; total success {total_success}, total fail {total_error}.", end='', flush=True)
    
    print(f'\n✅scan finished, success {total_success}, fail {total_error}')
    system_state.reset_scan_state()
    syncer = Syncer(db=AsyncSessionLocal(), settings=settings)
    for model in ['album', 'artist', 'folder', 'genre', 'track']:
        syncer.update_basic_sync_meta(model)

async def scan_music_library(root_path: str | Path):
    """scan music library"""
    reset_scan_cancel()
    files = []
    for file_path in Path(root_path).rglob('*'):
        if file_path.suffix.lower() in settings.MUSIC_FILE_EXTENSIONS:
            files.append(file_path)
    async with _scan_lock:
        await process_in_batches(files, Path(root_path))
    