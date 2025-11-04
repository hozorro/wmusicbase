# -*- encoding: utf-8 -*-
'''
@File      :   artwork.py
@Time      :   2025/10/20 14:10:02
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   deal artwork of track, artist and album
'''


import os
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import Track
from app.core.config import settings
from app.utils.metadata import extract_embedded_artwork
import logging

logger = logging.getLogger(__name__)

# 缓存目录
ARTWORK_DIR = settings.MEDIA_ROOT / 'artwork'
TRACK_ARTWORK_DIR = ARTWORK_DIR / 'tracks'
TRACK_ARTWORK_DIR.mkdir(parents=True, exist_ok=True)

async def get_or_cache_track_artwork(db: AsyncSession, track_id: int) -> Path | None:
    '''
    获取或生成Track封面缓存。
    返回缓存文件路径，如无封面则返回None
    '''
    cache_path = TRACK_ARTWORK_DIR / f'{track_id}.jpg'

    # 1. 检查缓存文件是否存在
    if cache_path.exists():
        # 可选：验证缓存是否仍有效（对比cover_art_hash）
        return cache_path
    
    # 2. 从数据库获取Track
    result = await db.execute(select(Track).where(Track.id == track_id))
    track = result.scalar_one_or_none()
    if not track or not track.cover_art_hash:
        return None
    
    # 3. 提取封面
    image_data = extract_embedded_artwork(track.path)
    if not image_data:
        return None
    
    # 4.保存为JPEG（统一格式）
    try:
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(image_data))
        # 转为RGB（处理RGBA/PNG）
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.save(cache_path, 'JPEG', quality=90)
        logger.info(f'Cached artwork for track {track_id} to {cache_path}')
        return cache_path
    except Exception as e:
        logger.error(f'Failed to save artwork for track {track_id}: {e}')
        return None
    
def invalidate_artwork_cache(track_id: int) -> bool:
    '''
    删除Track的封面缓存(如果存在)
    Args:
        track_id (int): Track的ID
    Returns:
        bool: 是否成功删除缓存, True表示文件存在并已删除，False表示缓存文件不存在
    '''
    cache_path = TRACK_ARTWORK_DIR / f'{track_id}.jpg'
    if cache_path.exists():
        try:
            cache_path.unlink()
            logger.info(f'Invalidated artwork cache for track {track_id}')
            return True
        except Exception as e:
            logger.error(f'Failed to delete artwork cache for track {track_id}: {e}')
            return False
    return False
        