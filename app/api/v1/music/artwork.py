# -*- encoding: utf-8 -*-
'''
@File      :   artwork.py
@Time      :   2025/10/20 14:09:12
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router artwork
'''


from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.services.artwork import get_or_cache_track_artwork
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get('/track/{track_id}', response_class=Response)
async def get_track_artwork(track_id: int, db: AsyncSession = Depends(get_db)):
    '''返回Track封面图片（JPEG）'''
    cache_path = await get_or_cache_track_artwork(db, track_id)
    if not cache_path or not cache_path.exists():
        raise HTTPException(status_code=404, detail='Track artwork not found')
    
    try:
        with open(cache_path, 'rb') as f:
            image_data = f.read()
        return Response(content=image_data, media_type='image/jpeg')
    except Exception as e:
        logger.error(f'Failed to read cached artwork for track {track_id}: {e}')
        raise HTTPException(status_code=500, detail='Failed to read cached artwork')