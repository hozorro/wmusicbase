# -*- encoding: utf-8 -*-
'''
@File      :   netease.py
@Time      :   2025/01/01 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   netease playlist import router
'''


from fastapi import APIRouter, Depends, status
from app.core.exceptions import BusinessException
from app.schemas.common import ResponseModel
from app.schemas.netease import (
    NeteasePlaylistResponse,
    NeteaseMatchRequest,
    NeteaseMatchResponse,
    NeteaseCreateRequest,
    NeteaseCreateResponse,
)
from app.services.netease_service import NeteaseService
from app.services.playback_service import PlaylistService

router = APIRouter()


@router.get('/playlist/{playlist_id}', response_model=ResponseModel[NeteasePlaylistResponse])
async def get_netease_playlist(
    playlist_id: int,
    service: NeteaseService = Depends(NeteaseService)
):
    '''
    fetch netease playlist info by id

    - **playlist_id**: netease playlist id

    Returns playlist info including name, cover image URL, and track list.
    Each track contains: name, artists, album, duration.
    '''
    result = await service.fetch_playlist(playlist_id)
    return ResponseModel(data=result)


@router.post('/match', response_model=ResponseModel[NeteaseMatchResponse])
async def match_netease_tracks(
    data: NeteaseMatchRequest,
    service: NeteaseService = Depends(NeteaseService)
):
    '''
    match netease tracks against local music library

    - **tracks**: list of netease track info (name, artists, album)

    Returns matched and unmatched tracks.
    For matched tracks, returns up to 5 local track candidates sorted by match precision.
    '''
    result = await service.match_tracks(data.tracks)
    return ResponseModel(data=result)


@router.post('/create', response_model=ResponseModel[NeteaseCreateResponse])
async def create_playlist_from_netease(
    data: NeteaseCreateRequest,
    netease_service: NeteaseService = Depends(NeteaseService),
    playlist_service: PlaylistService = Depends(PlaylistService)
):
    '''
    create new playlist from matched netease tracks

    - **title**: playlist title
    - **comment**: playlist comment (optional)
    - **cover_url**: cover image URL to download (optional)
    - **tracks**: list of local track ids in order

    Creates a new playlist and binds the specified tracks.
    If cover_url is provided, downloads and saves the cover image.
    '''
    # create playlist with tracks
    try:
        result = await playlist_service.create_playlist_and_bind_tracks(
            title=data.title,
            comment=data.comment,
            tracks=data.tracks
        )
    except Exception as e:
        raise BusinessException(
            code=30610,
            msg=f'error when create playlist: {str(e)}',
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    playlist = result['playlist']

    # download cover if provided
    if data.cover_url:
        try:
            await netease_service.download_cover(data.cover_url, playlist.id)
        except Exception as e:
            # log but don't fail the request
            from app.core.logger import logger
            logger.warning(f'Failed to download cover for playlist {playlist.id}: {e}')

    # get track count
    track_count = len(data.tracks) if data.tracks else 0

    return ResponseModel(data=NeteaseCreateResponse(
        id=playlist.id,
        title=playlist.title,
        cover_art_hash=playlist.cover_art_hash,
        track_count=track_count,
        created_at=playlist.created_at
    ))
