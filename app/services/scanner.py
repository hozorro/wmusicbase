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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError
from sqlalchemy import select, delete
from app.models import Track, Folder, Artist, Album, Genre, track_artists, track_genres
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.state import system_state
from typing import Any
import logging
from app.services.processor import MusicFileProcessor

# ========== 全局信号 ==========
_scan_cancel_event = asyncio.Event()
_scan_lock = asyncio.Lock()
MAX_RETRIES = 3

# ========== 控制接口 ==========
def cancel_scan():
    '''取消扫描任务'''
    _scan_cancel_event.set()

def reset_scan_cancel():
    '''重置取消信号'''
    _scan_cancel_event.clear()

# ========== 日志记录 ==========
logger = logging.getLogger(__name__)

async def get_track_by_path(db: AsyncSession, file_path: str) -> Track | None:
    '''根据文件绝对路径查找Track（包括已经软删除的）'''
    result = await db.execute(select(Track).where(Track.path == file_path))
    return result.scalar_one_or_none()

async def update_track(
    db: AsyncSession,
    track: Track,
    meta: dict[str, Any],
    cover_art_hash: str | None,
    folder: Folder,
    album: Album | None,
    artists: list[Artist],
    genres: list[Genre]
):
    '''更新已存在的Track及其关联关系'''
    # 1. 更新基础字段
    track.title = meta['title']
    track.duration = meta['duration']
    track.bitrate = meta['bitrate']
    track.bitrate_mode = meta['bitrate_mode']
    track.year = meta['year']
    track.acoustid_id = meta['acoustid_id']
    track.mb_trackid = meta['mb_trackid']
    track.cover_art_hash = cover_art_hash
    track.folder = folder
    track.album = album
    track.is_deleted = False # 若之前被软删除，恢复
    track.deleted_at = None

    # 2. 清除旧的多对多关系
    await db.execute(delete(track_artists).where(track_artists.c.track_id == track.id))
    await db.execute(delete(track_genres).where(track_genres.c.track_id == track.id))

    # 3. 重建多对多关系
    if artists:
        await db.execute(track_artists.insert().values([
            {'track_id': track.id, 'artist_id': artist.id} for artist in artists
        ]))
    if genres: 
        await db.execute(track_genres.insert().values([
            {'track_id': track.id, 'genre_id': genre.id} for genre in genres
        ]))
    await db.flush()

# ========== 扫描逻辑 ==============
async def process_in_batches(files: list[Path], root_path: Path, batch_size: int = 20):
    '''分批处理文件，每批提交一次事务'''
    semaphore = asyncio.Semaphore(batch_size) # 控制并发数

    async def process_file(file_path: Path):
        system_state.is_scanning = True
        system_state.scan_progress = {'total': 0, 'processed': 0}

        if _scan_cancel_event.is_set(): 
            return
        retries = 0
        while retries < MAX_RETRIES:
            try:
                async with semaphore:
                    if _scan_cancel_event.is_set(): 
                        return False
                    async with AsyncSessionLocal() as db:
                        processor = MusicFileProcessor(db)
                        result = await processor.process_single_file(file_path, root_path)
                        await db.commit()
                        return result
            except DBAPIError as e:
                if 'deadlock detected' in str(e):
                    retries += 1
                    await db.rollback()
                    logger.error(f"❌文件{file_path}发生Deadlock，  回滚并重试第{retries}次...")
                    await asyncio.sleep(0.1 * (retries + 1))
                    continue
                else:
                    await db.rollback()
                    logger.error(f"❌文件 {file_path} 处理失败并回滚: {e}")
                    return False
        print(f"❌文件{file_path}重试{MAX_RETRIES}后仍失败: {e}")
        return False
        
    total = len(files)
    system_state.init_scan_state()
    system_state.scan_progress['total'] = total
    total_batch_count = (total + batch_size - 1) // batch_size
    total_error = 0
    total_success = 0
    for i in range(0, total, batch_size):
        batch = files[i:i+batch_size]
        # 并发处理当前批次（限制并发数）        
        results = await asyncio.gather(*[process_file(file_path) for file_path in batch], return_exceptions=True)
        success = sum([1 for result in results if not isinstance(result, Exception)])
        error = len(batch) - success
        total_error += error
        total_success += success
        cur_batch = i // batch_size + 1
        system_state.scan_progress['processed'] = i + success + error
        system_state.scan_progress['success'] = total_success
        system_state.scan_progress['failed'] = total_error
        print(f"\r🔍总数: {total}; 已处理批次 {cur_batch}/{total_batch_count}: 成功 {success}/{len(batch)}; 总计成功 {total_success}, 总计失败 {total_error}。", end='', flush=True)
    
    print(f'\n✅扫描完成，成功 {total_success}, 失败 {total_error}')
    system_state.reset_scan_state()

async def scan_music_library(root_path: str | Path):
    """扫描媒体库"""
    reset_scan_cancel()
    files = []
    for file_path in Path(root_path).rglob('*'):
        if file_path.suffix.lower() in settings.MUSIC_FILE_EXTENSIONS:
            files.append(file_path)
    async with _scan_lock:
        await process_in_batches(files, Path(root_path))
    