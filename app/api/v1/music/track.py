# -*- encoding: utf-8 -*-
'''
@File      :   tracks.py
@Time      :   2025/10/20 14:04:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router tracks
'''


from fastapi import APIRouter, Depends, status
from app.schemas.common import ResponseModel, SuccessMsgModel
from app.schemas.track import TrackInfoResponse, TrackMoreInfoResponse
from app.schemas.common import TrackBrief
from app.services.track_service import TrackService
from app.core.exceptions import BusinessException


router = APIRouter()

@router.get('/signed-url/{track_id:int}', response_model=ResponseModel[str])
async def get_signed_url(track_id: int, service: TrackService = Depends(TrackService)):
    signed_url = await service.create_signed_url(track_id)
    return ResponseModel(data=signed_url)

@router.get('/{track_id:int}', response_model=ResponseModel[TrackInfoResponse])
async def get_track(track_id: int, service: TrackService = Depends(TrackService)):
    track = await service.get_track_info(track_id)
    if not track:
        raise BusinessException(
            code=30305, 
            msg='track not found', 
            status_code=status.HTTP_404_NOT_FOUND
        )
    return ResponseModel(data=TrackInfoResponse.model_validate(track))

@router.get('/moreinfo/{track_id:int}', response_model=ResponseModel[TrackMoreInfoResponse])
async def get_track_more_info(track_id: int, service: TrackService = Depends(TrackService)):
    track = await service.get_track_more_info(track_id)
    return ResponseModel(data=TrackMoreInfoResponse.model_validate(track))

@router.get('/randomtracks', response_model=ResponseModel[list[TrackBrief]])
async def get_random_tracks(num: int = 20, service: TrackService = Depends(TrackService)):
    tracks = await service.get_random_tracks(num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/artistrandomtracks', response_model=ResponseModel[list[TrackBrief]])
async def get_artist_random_tracks(artist_id: int, num: int = 20, service: TrackService = Depends(TrackService)):
    tracks = await service.get_artist_random_tracks(artist_id, num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/genrerandomtracks', response_model=ResponseModel[list[TrackBrief]])
async def get_genre_random_tracks(genre_id: int, num: int = 20, service: TrackService = Depends(TrackService)):
    tracks = await service.get_genre_random_tracks(genre_id, num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/favoritetracks', response_model=ResponseModel[list[TrackBrief]])
async def get_favorite_tracks(num: int | None = 100, service: TrackService = Depends(TrackService)):
    tracks = await service.get_favorite_tracks(num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/favoritetrackids', response_model=ResponseModel[list[int]])
async def get_favorite_track_ids(num: int | None = 100, service: TrackService = Depends(TrackService)):
    track_ids = await service.get_favorite_track_ids(num)
    return ResponseModel(data=track_ids)

@router.get('/latesttracks', response_model=ResponseModel[list[TrackBrief]])
async def get_latest_added_tracks(num: int | None = 12, service: TrackService = Depends(TrackService)):
    tracks = await service.get_latest_added_tracks(num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/mostplayedtracks', response_model=ResponseModel[list[TrackBrief]])
async def get_most_played_tracks(num: int | None = 12, service: TrackService = Depends(TrackService)):
    tracks = await service.get_most_played_tracks(num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/collection/{collection_type}/{collection_id:int}', response_model=ResponseModel[list[TrackBrief]])
async def get_collection_tracks(collection_type: str, collection_id: int, service: TrackService = Depends(TrackService)):
    tracks = await service.get_collection_tracks(collection_type, collection_id)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/lyric/{track_id:int}', response_model=ResponseModel[str | None])
async def get_lyric(track_id: int, service: TrackService = Depends(TrackService)):
    lyric = await service.get_lyric(track_id)
    return ResponseModel(data=lyric or '')

@router.delete('/lyric/{track_id:int}', response_model=ResponseModel[SuccessMsgModel])
async def delete_lyric(track_id: int, service: TrackService = Depends(TrackService)):
    await service.delete_lyric(track_id)
    return ResponseModel(data=SuccessMsgModel())
