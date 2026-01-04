# -*- encoding: utf-8 -*-
'''
@File      :   edit.py
@Time      :   2025/11/19 20:52:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   Edit music info from db
'''


from fastapi import APIRouter, Depends, HTTPException
from app.schemas.common import ResponseModel, SuccessMsgModel
from app.schemas.filething import UpdateMetaTagList
from app.schemas.artist import StartCharsResponse, ArtistsResponse, ArtistResponse, ArtistArtCreate, artist_art_upload_from_form
from app.schemas.album import AlbumResponse, AlbumArtCreate, album_art_upload_from_form
from app.core.deps import ADMIN_DEPS
from app.core.exceptions import BusinessException
from app.services.artwork_service import ArtworkService
from app.services.artist_service import ArtistService
from app.services.album_service import AlbumService
from app.services.track_service import TrackService

router = APIRouter(dependencies=ADMIN_DEPS)

@router.get('/getartistchars', response_model=ResponseModel[StartCharsResponse], tags=['edit'])
async def get_artist_chars(service: ArtistService = Depends(ArtistService)):
    start_chars = await service.get_artist_chars()
    return ResponseModel(data=StartCharsResponse(start_chars=start_chars))

@router.get('/getartists/{start_char}', response_model=ResponseModel[ArtistsResponse], tags=['edit'])
async def get_artists(start_char: str, without_path: bool, service: ArtistService = Depends(ArtistService)):
    artists = await service.get_start_char_artists(start_char, without_path)
    return ResponseModel(data=ArtistsResponse(artists=artists))

@router.get('/artist/{artist_id}', response_model=ResponseModel[ArtistResponse], tags=['edit'])
async def get_artist(artist_id: int, service: ArtistService = Depends(ArtistService)):
    artist = await service.get_artist(artist_id)
    if artist is None: 
        raise BusinessException(code=10004, msg='artist not exists', detail='artist id: ' + str(artist_id))
    return ResponseModel(data=ArtistResponse.model_validate(artist))

@router.get('/album/{album_id}', response_model=ResponseModel[AlbumResponse], tags=['edit'])
async def get_album(album_id: int, service: AlbumService = Depends(AlbumService)):
    album = await service.get_album_with_track_detail(album_id)
    if not album:
        raise BusinessException(code=10004, msg='album not exists', detail='album id: ' + str(album_id))
    return ResponseModel(data=AlbumResponse.model_validate(album))

@router.post('/uploadartistart', response_model=ResponseModel[SuccessMsgModel], tags=['edit'])
async def upload_artist_art(item: ArtistArtCreate = Depends(artist_art_upload_from_form), service: ArtworkService = Depends(ArtworkService)):
    if item.file.content_type not in ['image/jpeg', 'image/png']:
        raise HTTPException(status_code=400, detail='Only jpg and png files are allowed')
    try:
        await service.save_uploaded_artist_image(item.id, item.art_type, item.file)
        await item.file.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to save artist art: {str(e)}')
    return ResponseModel(data=SuccessMsgModel())

@router.post('/uploadalbumart', response_model=ResponseModel[SuccessMsgModel], tags=['edit'])
async def upload_album_art(item: AlbumArtCreate = Depends(album_art_upload_from_form), service: ArtworkService = Depends(ArtworkService)):
    if item.file.content_type not in ['image/jpeg', 'image/png']:
        raise HTTPException(status_code=400, detail='Only jpg and png files are allowed')
    try:
        await service.save_uploaded_album_image(item.id, item.file)
        await item.file.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to save album art: {str(e)}')
    return ResponseModel(data=SuccessMsgModel())

@router.post('/updatetrackfieldtag', response_model=ResponseModel[SuccessMsgModel], tags=['edit'])
async def update_track_field_tag(data: UpdateMetaTagList, service: TrackService = Depends(TrackService)):
    errors = await service.update_tracks_field_tag(data.items, data.field, data.value)
    if errors:
        raise BusinessException(code=10002, msg='partial success', detail='\n'.join(errors))
    return ResponseModel(data=SuccessMsgModel())