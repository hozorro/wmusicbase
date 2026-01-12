# -*- encoding: utf-8 -*-
'''
@File      :   tracks.py
@Time      :   2025/10/20 14:04:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router tracks
'''


from fastapi import APIRouter, Depends, HTTPException
from app.schemas.common import ResponseModel, SuccessMsgModel, StrResponse, TimeListResponse
from app.schemas.track import TrackBaseResponse, TrackBriefsResponse, TrackInfoResponse, TrackMoreInfoResponse, TrackFavRequest, TrackFavResponse, LyricResponse
from app.services.track_service import TrackService

router = APIRouter()

@router.get('/signed-url/{track_id:int}', response_model=ResponseModel[StrResponse])
async def get_signed_url(track_id: int, service: TrackService = Depends(TrackService)):
    signed_url = await service.create_signed_url(track_id)
    return ResponseModel(data=StrResponse(signed_url))
@router.get('/{track_id:int}', response_model=ResponseModel[TrackInfoResponse])
async def get_track(track_id: int, service: TrackService = Depends(TrackService)):
    track = await service.get_track_info(track_id)
    if not track:
        raise HTTPException(status_code=404, detail='Track not found')
    return ResponseModel(data=TrackInfoResponse.model_validate(track))
@router.get('/moreinfo/{track_id:int}', response_model=ResponseModel[TrackMoreInfoResponse])
async def get_track_more_info(track_id: int, service: TrackService = Depends(TrackService)):
    track = await service.get_track_more_info(track_id)
    return ResponseModel(data=TrackMoreInfoResponse.model_validate(track))
@router.get('/randomtracks', response_model=ResponseModel[TrackBriefsResponse])
async def get_random_tracks(num: int = 20, service: TrackService = Depends(TrackService)):
    tracks = await service.get_random_tracks(num)
    return ResponseModel(data=TrackBriefsResponse(tracks))

@router.get('/artistrandomtracks', response_model=ResponseModel[TrackBaseResponse])
async def get_artist_random_tracks(artist_id: int, num: int = 20, service: TrackService = Depends(TrackService)):
    tracks = await service.get_artist_random_tracks(artist_id, num)
    return ResponseModel(data=TrackBriefsResponse(tracks))

@router.get('/genrerandomtracks', response_model=ResponseModel[TrackBaseResponse])
async def get_genre_random_tracks(genre_id: int, num: int = 20, service: TrackService = Depends(TrackService)):
    tracks = await service.get_genre_random_tracks(genre_id, num)
    return ResponseModel(data=TrackBriefsResponse(tracks))

@router.get('/favoritetracks', response_model=ResponseModel[TrackBriefsResponse])
async def get_favorite_tracks(num: int | None = 50, service: TrackService = Depends(TrackService)):
    tracks = await service.get_favorite_tracks(num)
    return ResponseModel(data=TrackBriefsResponse(tracks))

@router.get('/latesttracks', response_model=ResponseModel[TrackBriefsResponse])
async def get_latest_added_tracks(num: int | None = 12, service: TrackService = Depends(TrackService)):
    tracks = await service.get_latest_added_tracks(num)
    return ResponseModel(data=TrackBriefsResponse(tracks))

@router.get('/mostplayedtracks', response_model=ResponseModel[TrackBriefsResponse])
async def get_most_played_tracks(num: int | None = 12, service: TrackService = Depends(TrackService)):
    tracks = await service.get_most_played_tracks(num)
    return ResponseModel(data=TrackBriefsResponse(tracks))

@router.put('/favorite/{track_id:int}', response_model=ResponseModel[TrackFavResponse])
async def favorite_track(track_id: int, fav_data: TrackFavRequest, service: TrackService = Depends(TrackService)):
    result = await service.favorite_track(track_id, fav_data.is_favorited)
    return ResponseModel(data=TrackFavResponse(result))

@router.get('/collection/{collection_type}/{collection_id:int}', response_model=ResponseModel[TrackBaseResponse])
async def get_collection_tracks(collection_type: str, collection_id: int, service: TrackService = Depends(TrackService)):
    tracks = await service.get_collection_tracks(collection_type, collection_id)
    return ResponseModel(data=TrackBaseResponse(tracks))

@router.get('/lyric/{track_id:int}', response_model=ResponseModel[LyricResponse])
async def get_lyric(track_id: int, service: TrackService = Depends(TrackService)):
    lyric = await service.get_lyric(track_id)
    if lyric: 
        return ResponseModel(data=LyricResponse(lyric))
    return ResponseModel(data=LyricResponse(''))

@router.delete('/lyric/{track_id:int}', response_model=ResponseModel[SuccessMsgModel])
async def delete_lyric(track_id: int, service: TrackService = Depends(TrackService)):
    await service.delete_lyric(track_id)
    return ResponseModel(data=SuccessMsgModel())

@router.get('/test/testtime', response_model=ResponseModel[TimeListResponse])
async def test_time_list(service: TrackService = Depends(TrackService)):
    dt_list = await service.get_tracks_hit_time()
    return ResponseModel(data=TimeListResponse(dt_list))