# -*- encoding: utf-8 -*-
'''
@File      :   artists.py
@Time      :   2025/10/20 14:06:38
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router artists
'''


from fastapi import APIRouter, Depends
from app.schemas.common import ResponseModel
from app.schemas.artist import ArtistsResponse, ArtistBriefListResponse, StartCharsResponse, ArtistDetailResponse
from app.services.artist_service import ArtistService

router = APIRouter()

@router.get('/tenartists', response_model=ResponseModel[ArtistsResponse])
async def get_ten_artists(service: ArtistService = Depends(ArtistService)):
    artists = await service.get_ten_artists()
    return ResponseModel(data=ArtistsResponse(artists))

@router.get('/artistchars', response_model=ResponseModel[StartCharsResponse])
async def get_start_chars(service: ArtistService = Depends(ArtistService)):
    start_chars = await service.get_artist_chars()
    return ResponseModel(data=StartCharsResponse(start_chars))

@router.get('/artists/{start_char}', response_model=ResponseModel[ArtistBriefListResponse])
async def get_artists(start_char: str, service: ArtistService = Depends(ArtistService)):
    artists = await service.get_start_char_artists(start_char)
    return ResponseModel(data=ArtistBriefListResponse(artists))

@router.get('/{artist_id}', response_model=ResponseModel[ArtistDetailResponse])
async def get_artist(artist_id: int, top: int | None = 20, service: ArtistService = Depends(ArtistService)):
    artist = await service.get_artist_detail(artist_id, top)
    return ResponseModel(data=ArtistDetailResponse.model_validate(artist))

@router.get('/favoritedartists', response_model=ResponseModel[ArtistsResponse])
async def get_favorited_artists(service: ArtistService = Depends(ArtistService)):
    artists = await service.get_favorited_artists()
    return ResponseModel(data=ArtistsResponse(artists))