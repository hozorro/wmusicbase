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
from app.schemas.common import ResponseModel, CountResponse
from app.schemas.sysinfo import MetaItem
from app.schemas.transfer import (
    TransferHitsList, TransferArtistHitCountsList, TransferFavsList,
    UploadPlaylists, UploadPlaylistsResponse,
    TransferAlbum, TransferArtist, TransferFolder, TransferGenre, TransferTrack,
    TransferHits, TransferArtistHitCounts, TransferFav,
    DownloadPlaylist
)
from app.schemas.transfer import TransferRequest

router = APIRouter()

@router.get('/getdbinfo', response_model=ResponseModel[list[MetaItem]])
async def get_db_info(service: TransferService = Depends(TransferService)):
    music_stats = await service.get_db_music_meta()
    return ResponseModel(data=[MetaItem.model_validate(s) for s in music_stats])

@router.get('/unsynccount', response_model=ResponseModel[CountResponse])
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
    return ResponseModel(data=CountResponse(count=count))

@router.post('/albums', response_model=ResponseModel[list[TransferAlbum]])
async def transfer_albums(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    albums = await service.transfer_albums(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=[TransferAlbum.model_validate(a) for a in albums])

@router.post('/artists', response_model=ResponseModel[list[TransferArtist]])
async def transfer_artists(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    artists = await service.transfer_artists(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=[TransferArtist.model_validate(a) for a in artists])

@router.post('/folders', response_model=ResponseModel[list[TransferFolder]])
async def transfer_folders(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    folders = await service.transfer_folders(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=[TransferFolder.model_validate(f) for f in folders])

@router.post('/genres', response_model=ResponseModel[list[TransferGenre]])
async def transfer_genres(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    genres = await service.transfer_genres(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=[TransferGenre.model_validate(g) for g in genres])

@router.post('/tracks', response_model=ResponseModel[list[TransferTrack]])
async def transfer_tracks(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    tracks = await service.transfer_tracks(req_data.last_sync, req_data.page_num, req_data.page_size)
    return ResponseModel(data=[TransferTrack.model_validate(t) for t in tracks])

@router.post('/upload/hits/track', response_model=ResponseModel[CountResponse])
async def upload_track_hits(hits: TransferHitsList, service: TransferService = Depends(TransferService)):
    count = await service.upload_track_hits(hits)
    return ResponseModel(data=CountResponse(count=count))

@router.post('/upload/hits/playlist', response_model=ResponseModel[CountResponse])
async def upload_playlist_hits(hits: TransferHitsList, service: TransferService = Depends(TransferService)):
    count = await service.upload_playlist_hits(hits)
    return ResponseModel(data=CountResponse(count=count))

@router.post('/upload/favs/track', response_model=ResponseModel[CountResponse])
async def upload_track_favs(favs: TransferFavsList, service: TransferService = Depends(TransferService)):
    count = await service.upload_track_favs(favs.added, favs.removed)
    return ResponseModel(data=CountResponse(count=count))

@router.post('/upload/favs/artist', response_model=ResponseModel[CountResponse])
async def upload_artist_favs(favs: TransferFavsList, service: TransferService = Depends(TransferService)):
    count = await service.upload_artist_favs(favs.added, favs.removed)
    return ResponseModel(data=CountResponse(count=count))

@router.post('/upload/playlists', response_model=ResponseModel[UploadPlaylistsResponse])
async def upload_playlists(playlists: UploadPlaylists, service: TransferService = Depends(TransferService)):
    result = await service.upload_playlists(playlists)
    return ResponseModel(data=UploadPlaylistsResponse.model_validate(result))
@router.get('/count/track/hits', response_model=ResponseModel[CountResponse])
async def get_track_hits_count(service: TransferService = Depends(TransferService)):
    count = await service.get_track_hits_records_count()
    return ResponseModel(data=CountResponse(count=count))
@router.get('/count/artist/hits', response_model=ResponseModel[CountResponse])
async def get_artist_hits_count(service: TransferService = Depends(TransferService)):
    count = await service.get_artist_hits_records_count()
    return ResponseModel(data=CountResponse(count=count))
@router.get('/count/playlist/hits', response_model=ResponseModel[CountResponse])
async def get_playlist_hits_count(service: TransferService = Depends(TransferService)):
    count = await service.get_playlist_hits_records_count()
    return ResponseModel(data=CountResponse(count=count))
@router.post('/download/track/hits', response_model=ResponseModel[list[TransferHits]])
async def download_track_hits(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    hits = await service.download_track_hits(req_data.page_num, req_data.page_size)
    return ResponseModel(data=[TransferHits.model_validate(h) for h in hits])
@router.post('/download/artist/hits', response_model=ResponseModel[list[TransferArtistHitCounts]])
async def download_artist_hits(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    hits = await service.download_artist_hits(req_data.page_num, req_data.page_size)
    return ResponseModel(data=[TransferArtistHitCounts.model_validate(h) for h in hits])
@router.post('/download/playlist/hits', response_model=ResponseModel[list[TransferHits]])
async def download_playlist_hits(req_data: TransferRequest, service: TransferService = Depends(TransferService)):
    hits = await service.download_playlist_hits(req_data.page_num, req_data.page_size)
    return ResponseModel(data=[TransferHits.model_validate(h) for h in hits])
@router.post('/download/track/favs', response_model=ResponseModel[TransferFavsList])
async def download_track_favs(service: TransferService = Depends(TransferService)):
    favs = await service.download_track_favs()
    return ResponseModel(data=TransferFavsList.model_validate(favs))
@router.post('/download/artist/favs', response_model=ResponseModel[TransferFavsList])
async def download_artist_favs(service: TransferService = Depends(TransferService)):
    favs = await service.download_artist_favs()
    return ResponseModel(data=TransferFavsList.model_validate(favs))
@router.post('/download/playlists', response_model=ResponseModel[list[DownloadPlaylist]])
async def download_playlists(service: TransferService = Depends(TransferService)):
    playlists = await service.download_playlists()
    return ResponseModel(data=[DownloadPlaylist.model_validate(p) for p in playlists])