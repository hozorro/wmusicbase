# -*- encoding: utf-8 -*-
'''
@File      :   tracks.py
@Time      :   2025/10/20 14:04:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router tracks
'''


from fastapi import APIRouter, Depends, Query, status
from app.schemas.common import ResponseModel
from app.schemas.track import TrackInfoResponse, TrackMoreInfoResponse, TracksPage, TrackSort
from app.schemas.common import TrackBrief
from app.services.track_service import (
    TrackService, HOME_TRACK_COUNT, clamp_tracks_num, normalize_pool,
)
from app.core.exceptions import BusinessException


router = APIRouter()

# 静态路由统一声明在 /{track_id:int} 之前，避免被动态段抢先匹配
@router.get('/tracks', response_model=ResponseModel[TracksPage])
async def get_tracks_by_sort(
    sort: TrackSort = Query('latest', description='latest | hot | history'),
    page: int = Query(1, ge=1, description='page number'),
    page_size: int = Query(20, ge=1, le=100, description='page size'),
    service: TrackService = Depends(TrackService),
):
    '''全部曲目：三种排序 + 稳定次级键 id DESC 的偏移分页'''
    total, tracks = await service.get_sorted_tracks(sort, page, page_size)
    return ResponseModel(data=TracksPage(
        total=total,
        page=page,
        page_size=page_size,
        sort=sort,
        tracks=[TrackBrief.model_validate(t) for t in tracks],
    ))

@router.get('/rndfreshtracks', response_model=ResponseModel[list[TrackBrief]])
async def get_rnd_fresh_tracks(
    num: int = Query(50, ge=1, le=200),
    pool: int = Query(500, ge=1, le=10000),
    service: TrackService = Depends(TrackService),
):
    '''新鲜模式：最近添加的 pool 首为候选池，随机取 num 首；pool 夹到 100~1000 并按 100 取整'''
    tracks = await service.get_rnd_fresh_tracks(clamp_tracks_num(num), normalize_pool(pool))
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/rndartisttracks', response_model=ResponseModel[list[TrackBrief]])
async def get_rnd_artist_tracks(
    num: int = Query(50, ge=1, le=200),
    numpa: int = Query(1, ge=1, le=20),
    service: TrackService = Depends(TrackService),
):
    '''随机歌手散布取歌：每位歌手 ≤ numpa 首，跨歌手去重，总量 num'''
    tracks = await service.get_rnd_artist_scattered_tracks(num, numpa)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/rndunhittracks', response_model=ResponseModel[list[TrackBrief]])
async def get_rnd_unhit_tracks(
    num: int = Query(50, ge=1, le=200),
    service: TrackService = Depends(TrackService),
):
    '''随机取当前用户从未播放过的曲目'''
    tracks = await service.get_rnd_unhit_tracks(num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/rndwgttracks', response_model=ResponseModel[list[TrackBrief]])
async def get_rnd_weighted_artist_tracks(
    num: int = Query(50, ge=1, le=200),
    weight: int = Query(5, ge=1, le=20),
    service: TrackService = Depends(TrackService),
):
    '''按曲目数加权随机歌手，每人一首，展平为 Track[]（与本地 IDB 同形状）'''
    tracks = await service.get_rnd_weighted_artist_tracks(num, weight)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/rndhitswgttracks', response_model=ResponseModel[list[TrackBrief]])
async def get_rnd_hits_weighted_tracks(
    num: int = Query(50, ge=1, le=200),
    weight: int = Query(5, ge=1, le=20),
    service: TrackService = Depends(TrackService),
):
    '''按 (1 + 播放次数)^α 加权随机曲目，未播放曲目恒有机会'''
    tracks = await service.get_rnd_weighted_hit_tracks(num, weight)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

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
async def get_favorite_tracks(num: int = 100, service: TrackService = Depends(TrackService)):
    tracks = await service.get_favorite_tracks(num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/favoritetrackids', response_model=ResponseModel[list[int]])
async def get_favorite_track_ids(num: int = 100, service: TrackService = Depends(TrackService)):
    track_ids = await service.get_favorite_ids(num)
    return ResponseModel(data=track_ids)

@router.get('/latesttracks', response_model=ResponseModel[list[TrackBrief]])
async def get_latest_added_tracks(
    num: int = Query(HOME_TRACK_COUNT, ge=1, le=100),
    service: TrackService = Depends(TrackService),
):
    tracks = await service.get_latest_added_tracks(num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/mostplayedtracks', response_model=ResponseModel[list[TrackBrief]])
async def get_most_played_tracks(
    num: int = Query(HOME_TRACK_COUNT, ge=1, le=100),
    service: TrackService = Depends(TrackService),
):
    tracks = await service.get_most_played_tracks(num)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/collection/{collection_type}/{collection_id:int}', response_model=ResponseModel[list[TrackBrief]])
async def get_collection_tracks(collection_type: str, collection_id: int, service: TrackService = Depends(TrackService)):
    tracks = await service.get_collection_tracks(collection_type, collection_id)
    return ResponseModel(data=[TrackBrief.model_validate(t) for t in tracks])

@router.get('/lyric/{track_id:int}', response_model=ResponseModel[str])
async def get_lyric(track_id: int, service: TrackService = Depends(TrackService)):
    '''lyric text of a track, an empty string means the track has no lyric yet'''
    lyric = await service.get_lyric(track_id)
    return ResponseModel(data=lyric)
