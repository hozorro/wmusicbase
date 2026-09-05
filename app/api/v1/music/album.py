# -*- encoding: utf-8 -*-
'''
@File      :   albums.py
@Time      :   2025/10/20 14:05:34
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router albums
'''


from asyncache import cached
from fastapi import APIRouter, Depends, status
from app.core.cache import lru_cache
from app.core.exceptions import BusinessException
from app.schemas.common import ResponseModel
from app.schemas.album import AlbumDetail
from app.services.album_service import AlbumService

router = APIRouter()

@router.get("/{album_id}", response_model=ResponseModel[AlbumDetail])
@cached(lru_cache)
async def get_album(album_id: int, service: AlbumService = Depends(AlbumService)):
    album = await service.get_album(album_id)
    if not album:
        raise BusinessException(
            code=30204, 
            msg=f'album not exists: {album_id}', 
            detail={'album_id': album_id},
            status_code=status.HTTP_404_NOT_FOUND
        )
    return ResponseModel(data=AlbumDetail.model_validate(album))