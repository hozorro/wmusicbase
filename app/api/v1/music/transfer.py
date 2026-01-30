# -*- encoding: utf-8 -*-
'''
@File      :   stat.py
@Time      :   2025/12/08 16:11:12
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   route: transfer musicbase data to client
'''


from datetime import datetime
# from cachetools import cached
from fastapi import APIRouter, Depends, HTTPException
# from app.core.cache import lru_cache
from app.services.transfer_service import TransferService
from app.schemas.common import ResponseModel, NumResponse
from app.schemas.sysinfo import MusicStatInfo, TransferRequest
from app.schemas.transfer import (
    TransferAlbumListResponse, TransferArtistListResponse, TransferFolderListResponse, 
    TransferGenreListResponse, TransferTrackListResponse, 
    TransferHitsList, TransferArtistHitCountsList, TransferFavsList,
    UploadPlaylists, UploadPlaylistsResponse, DownloadPlaylistListsResponse
)

router = APIRouter()

@router.get('/getdbinfo', response_model=ResponseModel[MusicStatInfo])
async def get_db_info(service: TransferService = Depends(TransferService)):
    music_stats = await service.get_db_music_meta()
    return ResponseModel(data=MusicStatInfo(music_stats))

@router.get('/unsynccount', response_model=ResponseModel[NumResponse])
# @cached(lru_cache)
async def get_unsync_count(entity: str, last_sync: datetime | None = None, service: TransferService = Depends(TransferService)):
    '''
    get unsynced count of entity
    entity: str, could be album, artist, folder, genre, track
    '''
    if last_sync is None:
        last_sync = datetime.min
    if entity in ['album', 'artist', 'folder', 'genre', 'track']:
        count = await service.get_unsync_count(entity, last_sync)
    else:
        raise HTTPException(status_code=400, detail='Invalid entity')
    return ResponseModel(data=NumResponse(count))

@router.post('/albums', response_model=ResponseModel[TransferAlbumListResponse])
async def transfer_albums(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    albums = await service.transfer_albums(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=TransferAlbumListResponse.model_validate(albums))

@router.post('/artists', response_model=ResponseModel[TransferArtistListResponse])
async def transfer_artists(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    artists = await service.transfer_artists(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=TransferArtistListResponse.model_validate(artists))

@router.post('/folders', response_model=ResponseModel[TransferFolderListResponse])
async def transfer_folders(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    folders = await service.transfer_folders(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=TransferFolderListResponse.model_validate(folders))

@router.post('/genres', response_model=ResponseModel[TransferGenreListResponse])
async def transfer_genres(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    genres = await service.transfer_genres(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=TransferGenreListResponse.model_validate(genres))

@router.post('/tracks', response_model=ResponseModel[TransferTrackListResponse])
async def transfer_tracks(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    tracks = await service.transfer_tracks(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=TransferTrackListResponse.model_validate(tracks))

@router.post('/upload/hits/track', response_model=ResponseModel[NumResponse])
async def upload_track_hits(hits: TransferHitsList, service: TransferService = Depends(TransferService)):
    count = await service.upload_track_hits(hits)
    return ResponseModel(data=NumResponse(count))

@router.post('/upload/hits/playlist', response_model=ResponseModel[NumResponse])
async def upload_playlist_hits(hits: TransferHitsList, service: TransferService = Depends(TransferService)):
    count = await service.upload_playlist_hits(hits)
    return ResponseModel(data=NumResponse(count))

@router.post('/upload/favs/track', response_model=ResponseModel[NumResponse])
async def upload_track_favs(favs: TransferFavsList, service: TransferService = Depends(TransferService)):
    count = await service.upload_track_favs(favs.added, favs.removed)
    return ResponseModel(data=NumResponse(count))

@router.post('/upload/favs/artist', response_model=ResponseModel[NumResponse])
async def upload_artist_favs(favs: TransferFavsList, service: TransferService = Depends(TransferService)):
    count = await service.upload_artist_favs(favs.added, favs.removed)
    return ResponseModel(data=NumResponse(count))

@router.post('/upload/playlists', response_model=ResponseModel[UploadPlaylistsResponse])
async def upload_playlists(playlists: UploadPlaylists, service: TransferService = Depends(TransferService)):
    result = await service.upload_playlists(playlists)
    return ResponseModel(data=UploadPlaylistsResponse.model_validate(result))
@router.get('/count/track/hits', response_model=ResponseModel[NumResponse])
async def get_track_hits_count(service: TransferService = Depends(TransferService)):
    count = await service.get_track_hits_records_count()
    return ResponseModel(data=NumResponse(count))
@router.get('/count/artist/hits', response_model=ResponseModel[NumResponse])
async def get_artist_hits_count(service: TransferService = Depends(TransferService)):
    count = await service.get_artist_hits_records_count()
    return ResponseModel(data=NumResponse(count))
@router.get('/count/playlist/hits', response_model=ResponseModel[NumResponse])
async def get_playlist_hits_count(service: TransferService = Depends(TransferService)):
    count = await service.get_playlist_hits_records_count()
    return ResponseModel(data=NumResponse(count))
@router.post('/download/track/hits', response_model=ResponseModel[TransferHitsList])
async def download_track_hits(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    hits = await service.download_track_hits(req_data.page_num, req_data.page_size)
    return ResponseModel(data=TransferHitsList.model_validate(hits))
@router.post('/download/artist/hits', response_model=ResponseModel[TransferArtistHitCountsList])
async def download_artist_hits(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    hits = await service.download_artist_hits(req_data.page_num, req_data.page_size)
    return ResponseModel(data=TransferArtistHitCountsList.model_validate(hits))
@router.post('/download/playlist/hits', response_model=ResponseModel[TransferHitsList])
async def download_playlist_hits(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    hits = await service.download_playlist_hits(req_data.page_num, req_data.page_size)
    return ResponseModel(data=TransferHitsList.model_validate(hits))
@router.post('/download/track/favs', response_model=ResponseModel[TransferFavsList])
async def download_track_favs(service: TransferService = Depends(TransferService)):
    favs = await service.download_track_favs()
    return ResponseModel(data=TransferFavsList.model_validate(favs))
@router.post('/download/artist/favs', response_model=ResponseModel[TransferFavsList])
async def download_artist_favs(service: TransferService = Depends(TransferService)):
    favs = await service.download_artist_favs()
    return ResponseModel(data=TransferFavsList.model_validate(favs))
@router.post('/download/playlists', response_model=ResponseModel[DownloadPlaylistListsResponse])
async def download_playlists(service: TransferService = Depends(TransferService)):
    playlists = await service.download_playlists()
    return ResponseModel(data=DownloadPlaylistListsResponse.model_validate(playlists))