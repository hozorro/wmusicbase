# -*- encoding: utf-8 -*-
'''
@File      :   playback.py
@Time      :   2025/06/23 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router playback (playlist, hit, favorite)
'''


from datetime import datetime
from fastapi import APIRouter, Depends, status
from app.core.exceptions import BusinessException
from app.schemas.common import ResponseModel, SuccessMsgModel, PlaylistBase
from app.schemas.playback import (
    PlaylistResponse,
    PlaylistWithTracksResponse,
    PlaylistCreate,
    playlist_create_with_art_form,
    PlaylistUpdate,
    playlist_update_with_art_form,
    TrackToPlaylistRequest,
    PlaylistDeleteRequest,
    MovePlaylistTrackRequest,
    TrackHitRequest,
    ArtistHitRequest,
    PlaylistHitRequest,
    TrackFavRequest,
    ArtistFavRequest,
)
from app.services.playback_service import PlaylistService, PlayBackService
from app.services.artwork_service import ArtworkService

router = APIRouter()

# ============ Playlist ============

@router.get('/topplaylists', response_model=ResponseModel[list[PlaylistBase]])
async def get_top_playlists(service: PlaylistService = Depends(PlaylistService)):
    playlists = await service.get_top_playlists()
    return ResponseModel(data=[PlaylistBase.model_validate(p) for p in playlists])

@router.get('/playlists', response_model=ResponseModel[list[PlaylistBase]])
async def get_playlists(service: PlaylistService = Depends(PlaylistService)):
    playlists = await service.get_user_playlists()
    return ResponseModel(data=[PlaylistBase.model_validate(p) for p in playlists])

@router.get('/{playlist_id}', response_model=ResponseModel[PlaylistWithTracksResponse])
async def get_playlist(playlist_id: int, service: PlaylistService = Depends(PlaylistService)):
    playlist = await service.get_playlist_info(playlist_id)
    return ResponseModel(data=PlaylistWithTracksResponse.model_validate(playlist))

@router.post('/addplaylist', response_model=ResponseModel[PlaylistResponse | SuccessMsgModel])
async def add_playlist(
    create_data: PlaylistCreate = Depends(playlist_create_with_art_form), 
    playlist_service: PlaylistService = Depends(PlaylistService),
    artwork_service: ArtworkService = Depends(ArtworkService)
):
    result = {}
    try:
        result = await playlist_service.create_playlist_and_bind_tracks(create_data.title, create_data.comment)
    except Exception:
        raise BusinessException(
            code=30507, 
            msg='error when create playlist', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )
    
    if create_data.cover and result:
        try:
            if create_data.cover.content_type not in ['image/jpeg', 'image/png']:
                raise BusinessException(
                    code=30515, 
                    msg='only jpg and png files are allowed for playlist images', 
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, 
                )
            await artwork_service.save_uploaded_playlist_image(result['playlist'].id, create_data.cover)
        except Exception as e:
            return ResponseModel(data=SuccessMsgModel(info='Playlist created successfully, but failed to save playlist image'))
    
    return ResponseModel(data=PlaylistResponse.model_validate(result['playlist']))

@router.put('/updateplaylist', response_model=ResponseModel[PlaylistResponse | SuccessMsgModel])
async def edit_playlist(
    data: PlaylistUpdate = Depends(playlist_update_with_art_form), 
    service: PlaylistService = Depends(PlaylistService),
    artwork_service: ArtworkService = Depends(ArtworkService)
):
    try:
        playlist = await service.update_playlist(data.id, data.title, data.comment)
    except Exception:
        raise BusinessException(
            code=30508, 
            msg='error when update playlist', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )
    
    if data.cover:
        try:
            if data.cover.content_type not in ['image/jpeg', 'image/png']:
                raise BusinessException(
                    code=30515, 
                    msg='only jpg and png files are allowed for playlist images', 
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, 
                )
            await artwork_service.save_uploaded_playlist_image(data.id, data.cover)
        except Exception:
            raise BusinessException(
                code=30509, 
                msg='update successful but error when save playlist image', 
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            )
    
    return ResponseModel(data=PlaylistResponse.model_validate(playlist))

@router.delete('/deleteplaylist', response_model=ResponseModel[SuccessMsgModel])
async def delete_playlist(data: PlaylistDeleteRequest, service: PlaylistService = Depends(PlaylistService)):
    await service.delete_playlist(data.id)
    return ResponseModel(data=SuccessMsgModel())

@router.post('/addplaylistsimple', response_model=ResponseModel[SuccessMsgModel])
async def add_playlist_simple(
    data: PlaylistCreate,
    service: PlaylistService = Depends(PlaylistService)
):
    result = await service.create_playlist_and_bind_tracks(data)
    return ResponseModel(data=PlaylistResponse.model_validate(result.playlist))

@router.put('/addtracktoplaylist', response_model=ResponseModel[SuccessMsgModel])
async def add_track_to_playlist(data: TrackToPlaylistRequest, service: PlaylistService = Depends(PlaylistService)):
    result = await service.add_track_to_playlist(data.playlist_id, data.track_id)
    if not result:
        raise BusinessException(
            code=30509, 
            msg='track already exists in playlist', 
            status_code=status.HTTP_409_CONFLICT, 
        )
    return ResponseModel(data=SuccessMsgModel())

@router.put('/removetrackfromplaylist', response_model=ResponseModel[SuccessMsgModel])
async def remove_track_from_playlist(data: TrackToPlaylistRequest, service: PlaylistService = Depends(PlaylistService)):
    await service.remove_track_from_playlist(data.playlist_id, data.track_id)
    return ResponseModel(data=SuccessMsgModel())

@router.put('/moveplaylisttrack', response_model=ResponseModel[SuccessMsgModel])
async def move_playlist_track(data: MovePlaylistTrackRequest, service: PlaylistService = Depends(PlaylistService)):
    await service.move_playlist_track(data.id, data.track_id, data.new_position)
    return ResponseModel(data=SuccessMsgModel())

# ============ Hit (play record) ============

@router.put('/updatetrackhit', response_model=ResponseModel[SuccessMsgModel])
async def update_track_hit(data: TrackHitRequest, service: PlayBackService = Depends(PlayBackService)):
    await service.add_track_hit(data.track_id)
    return ResponseModel(data=SuccessMsgModel())

@router.get('/gettrackhits/{track_id}', response_model=ResponseModel[list[datetime]])
async def get_track_hits(track_id: int, service: PlayBackService = Depends(PlayBackService)):
    hits = await service.get_track_hits(track_id)
    return ResponseModel(data=hits)

@router.put('/updateartisthit', response_model=ResponseModel[SuccessMsgModel])
async def update_artist_hit(data: ArtistHitRequest, service: PlayBackService = Depends(PlayBackService)):
    await service.add_artist_hit(data.artist_id)
    return ResponseModel(data=SuccessMsgModel())

@router.put('/updateplaylisthit', response_model=ResponseModel[SuccessMsgModel])
async def update_playlist_hit(data: PlaylistHitRequest, service: PlayBackService = Depends(PlayBackService)):
    await service.add_playlist_hit(data.playlist_id)
    return ResponseModel(data=SuccessMsgModel())

# ============ Favorite ============

@router.put('/favoritetrack', response_model=ResponseModel[datetime | None])
async def favorite_track(data: TrackFavRequest, service: PlayBackService = Depends(PlayBackService)):
    result = await service.favorite_track(data.track_id, data.is_favorited)
    return ResponseModel(data=result)

@router.put('/favoriteartist', response_model=ResponseModel[datetime | None])
async def favorite_artist(data: ArtistFavRequest, service: PlayBackService = Depends(PlayBackService)):
    result = await service.favorite_artist(data.artist_id, data.is_favorited)
    return ResponseModel(data=result)
