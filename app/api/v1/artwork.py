# -*- encoding: utf-8 -*-
'''
@File      :   artwork.py
@Time      :   2025/11/21 22:10:39
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   uniformed artwork provider
'''


from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from app.services.artwork_service import ArtworkService

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
async def get_playlist_artwork(playlist_id: int, service: ArtworkService = Depends(ArtworkService)):
    cache_path = await service.get_or_cache_playlist_artwork(playlist_id)
    if cache_path: 
        return FileResponse(cache_path)
    raise HTTPException(status_code=404, detail='Playlist artwork not Found')
