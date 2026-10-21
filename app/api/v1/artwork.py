# -*- encoding: utf-8 -*-
'''
@File      :   artwork.py
@Time      :   2025/11/21 22:10:39
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   uniformed artwork provider
'''


# The system will try to find cover art for every entity and cache it.
# If the cover art is not found, the system will try to set the default cover art.
# If the default cover art is not found, the system will raise a 404 error.
# If the frontend receives a 404 error, it will display the default cover art by itself.
# So the backend default artwork will be priority to the frontend default artwork.

from fastapi import APIRouter, Depends, Query, Response, UploadFile, Form, status
from fastapi.responses import FileResponse
from app.core.config import settings
from app.schemas.common import ResponseModel, SuccessMsgModel
from app.services.artwork_service import ArtworkService
from app.services.fetchcoverart import get_cover_art, cover_cache
from app.core.exceptions import BusinessException

router = APIRouter()

@router.get('/artist/{artist_id}', tags=['artwork'])
async def get_artist_artwork(artist_id: int, img_cate: str, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_or_cache_artist_artwork(artist_id, img_cate)
    if cache_path: 
        return FileResponse(cache_path)
    raise BusinessException(
        code=60104,
        msg='artist artwork not found',
        status_code=status.HTTP_404_NOT_FOUND
    )
    
@router.get('/track/{track_id}', tags=['artwork'])
async def get_track_artwork(track_id: int, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_or_cache_track_artwork(track_id)
    if cache_path: 
        return FileResponse(cache_path)
    raise BusinessException(
        code=60304,
        msg='track artwork not found',
        status_code=status.HTTP_404_NOT_FOUND
    )
    
@router.get('/album/{album_id}', tags=['artwork'])
async def get_album_artwork(album_id: int, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_or_cache_album_artwork(album_id)
    if cache_path: 
        return FileResponse(cache_path)
    raise BusinessException(
        code=60204,
        msg='album artwork not found',
        status_code=status.HTTP_404_NOT_FOUND
    )

@router.get('/playlist/{playlist_id}', tags=['artwork'])
async def get_playlist_artwork(playlist_id: int | str, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_or_cache_playlist_artwork(playlist_id)
    if cache_path: 
        return FileResponse(cache_path)
    raise BusinessException(
        code=60504,
        msg='playlist artwork not found',
        status_code=status.HTTP_404_NOT_FOUND
    )

@router.get('/staging/{release_id}')
async def get_cover(release_id: str):
    try:
        cover_data = get_cover_art(release_id)
    except Exception:
        raise BusinessException(
            code=60205, 
            msg='cover art fetch error', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    if cover_data is None:
        raise BusinessException(
            code=60206, 
            msg='cover art not found', 
            status_code=status.HTTP_404_NOT_FOUND
        )
    return Response(
        content=cover_data,
        media_type='image/jpeg',
        headers={
            'Cache-Control': f'max-age={settings.CACHE_EXPIRE}',
            'X-Cache-Status': 'HIT' if release_id in cover_cache else 'MISS'
        }
    )
@router.get('/tmp/track/{path}', tags=['artwork'])
async def get_tmp_track_artwork(
    path: str, 
    session_id: str = Query(..., description='Session ID'),
    service: ArtworkService = Depends(ArtworkService)
):
    from app.core.config import settings
    file_path = settings.STAGING_DIR / session_id / 'songs' / path
    cache_path = await service.get_or_cache_tmp_track_artwork(str(file_path))
    if cache_path: 
        return FileResponse(cache_path)
    raise BusinessException(
        code=60305, 
        msg='tmp track artwork not found', 
        status_code=status.HTTP_404_NOT_FOUND
    )

@router.get('/tmp/artist/{temp_id}', tags=['artwork'])
async def get_tmp_artist_artwork(
    temp_id: str,
    service: ArtworkService = Depends(ArtworkService)
):
    '''serve temp artist artwork image'''
    file_path = service.get_tmp_artist_artwork_path(temp_id)
    if not file_path:
        raise BusinessException(
            code=60123,
            msg='temp artwork not found or expired',
            status_code=status.HTTP_404_NOT_FOUND
        )
    return FileResponse(
        file_path,
        headers={'Cache-Control': 'no-cache'}
    )

@router.get('/default/{art_type}', tags=['artwork'])
async def get_default_artwork(art_type: str, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_default_art(art_type)
    if cache_path: 
        return FileResponse(cache_path)
    raise BusinessException(
        code=60404, 
        msg='default artwork not found', 
        status_code=status.HTTP_404_NOT_FOUND
    )

@router.get('/candidates/{artist_id}/{filename}', tags=['artwork'])
async def get_artist_art_candidate(
    artist_id: int,
    filename: str,
    service: ArtworkService = Depends(ArtworkService)
):
    '''serve candidate artwork image for an artist (admin only)'''
    file_path = await service.get_artist_candidate_file(artist_id, filename)
    if not file_path:
        raise BusinessException(
            code=60105, 
            msg='candidate artist artwork not found', 
            status_code=status.HTTP_404_NOT_FOUND
        )
    return FileResponse(
        file_path,
        headers={'Cache-Control': 'no-cache'}  # no caching since frontend uses ?t= timestamp
    )

@router.post('/default', response_model=ResponseModel[SuccessMsgModel], tags=['edit'])
async def set_default_art(cover: UploadFile, art_type: str = Form(...), service: ArtworkService = Depends(ArtworkService)):
    try:
        if cover.content_type not in ['image/jpeg', 'image/png']:
            raise BusinessException(
                code=60415, 
                msg='only jpg and png files are allowed', 
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            )
        await service.set_default_art(art_type, cover)
        return ResponseModel(data=SuccessMsgModel())
    except Exception as e:
        raise BusinessException(
            code=60405, 
            msg='failed to set default artwork', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
