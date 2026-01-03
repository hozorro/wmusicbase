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
from app.core.logger import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError
from app.core.db import safe_async_transaction
from sqlalchemy import select
from app.models import Track
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.state import system_state
from app.services.processor import MusicFileProcessor

# ========== global signals ==========
_scan_cancel_event = asyncio.Event()
_scan_lock = asyncio.Lock()
MAX_RETRIES = 3

# ========== control interface =======
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
        system_state.is_scanning = True
        system_state.scan_progress = {'total': 0, 'processed': 0}

        if _scan_cancel_event.is_set(): 
            return

        async with semaphore:
            if _scan_cancel_event.is_set(): 
                return False
            async with AsyncSessionLocal() as db:
                try:
                    processor = MusicFileProcessor(root_path, db)
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
        system_state.scan_progress['processed'] = i + success + error
        system_state.scan_progress['success'] = total_success
        system_state.scan_progress['failed'] = total_error
        print(f"\r🔍Total: {total}; handled batches {cur_batch}/{total_batch_count}: success {success}/{len(batch)}; total success {total_success}, total fail {total_error}.", end='', flush=True)
    
    print(f'\n✅scan finished, success {total_success}, fail {total_error}')
    system_state.reset_scan_state()

async def scan_music_library(root_path: str | Path):
    """scan music library"""
    reset_scan_cancel()
    files = []
    for file_path in Path(root_path).rglob('*'):
        if file_path.suffix.lower() in settings.MUSIC_FILE_EXTENSIONS:
            files.append(file_path)
    async with _scan_lock:
        await process_in_batches(files, Path(root_path))
    