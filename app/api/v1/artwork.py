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

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, Form
from fastapi.responses import FileResponse
from app.core.config import settings
from app.core.deps import ADMIN_DEPS
from app.schemas.common import ResponseModel, SuccessMsgModel
from app.services.artwork_service import ArtworkService
from app.services.fetchcoverart import get_cover_art, cover_cache

router = APIRouter()

@router.get('/artist/{artist_id}', tags=['artwork'])
async def get_artist_artwork(artist_id: int, img_cate: str, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_or_cache_artist_artwork(artist_id, img_cate)
    if cache_path: 
        return FileResponse(cache_path)
    raise HTTPException(status_code=404, detail='Artist artwork not Found')
    
@router.get('/track/{track_id}', tags=['artwork'])
async def get_track_artwork(track_id: int, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_or_cache_track_artwork(track_id)
    if cache_path: 
        return FileResponse(cache_path)
    raise HTTPException(status_code=404, detail='Track artwork not Found')
    
@router.get('/album/{album_id}', tags=['artwork'])
async def get_album_artwork(album_id: int, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_or_cache_album_artwork(album_id)
    if cache_path: 
        return FileResponse(cache_path)
    raise HTTPException(status_code=404, detail='Album artwork not Found')

@router.get('/playlist/{playlist_id}', tags=['artwork'])
async def get_playlist_artwork(playlist_id: int | str, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_or_cache_playlist_artwork(playlist_id)
    if cache_path: 
        return FileResponse(cache_path)
    raise HTTPException(status_code=404, detail='Playlist artwork not Found')

@router.get('/staging/{release_id}')
async def get_cover(release_id: str):
    try:
        cover_data = get_cover_art(release_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Error when fetch cover art: {str(e)}')
    if cover_data is None:
        raise HTTPException(status_code=404, detail='Cover art not found')
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
    raise HTTPException(status_code=404, detail=f'Tmp Track artwork not Found: {file_path}')

@router.get('/default/{art_type}', tags=['artwork'])
async def get_default_artwork(art_type: str, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_default_art(art_type)
    if cache_path: 
        return FileResponse(cache_path)
    raise HTTPException(status_code=404, detail='Default artwork not Found')

@router.get('/candidates/{artist_id}/{filename}', tags=['artwork'])
async def get_artist_art_candidate(
    artist_id: int,
    filename: str,
    service: ArtworkService = Depends(ArtworkService)
):
    '''serve candidate artwork image for an artist (admin only)'''
    file_path = await service.get_artist_candidate_file(artist_id, filename)
    if not file_path:
        raise HTTPException(status_code=404, detail='Candidate artwork not found')
    return FileResponse(
        file_path,
        headers={'Cache-Control': 'no-cache'}  # no caching since frontend uses ?t= timestamp
    )

@router.post('/default', response_model=ResponseModel[SuccessMsgModel], tags=['edit'])
async def set_default_art(cover: UploadFile, art_type: str = Form(...), service: ArtworkService = Depends(ArtworkService)):
    try:
        if cover.content_type not in ['image/jpeg', 'image/png']:
            raise HTTPException(status_code=400, detail='Only jpg and png files are allowed')
        await service.set_default_art(art_type, cover)
        return ResponseModel(data=SuccessMsgModel())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to set default {art_type} art.')