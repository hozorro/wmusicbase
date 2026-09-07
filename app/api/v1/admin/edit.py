# -*- encoding: utf-8 -*-
'''
@File      :   edit.py
@Time      :   2025/11/19 20:52:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   Edit music info from db
'''


from fastapi import APIRouter, Depends, UploadFile, Form, File, status
from pydantic import BaseModel
from app.schemas.common import ResponseModel, SuccessMsgModel, CountResponse, ArtistBase
from app.schemas.filething import UpdateMetaTagList
from app.schemas.artist import ArtistResponse, ArtistArtCreate, artist_art_upload_from_form, ArtistArtUpdate
from app.schemas.album import AlbumResponse, AlbumArtCreate, album_art_upload_from_form
from app.core.exceptions import BusinessException
from app.core.deps import ADMIN_DEPS
from app.services.artwork_service import ArtworkService
from app.services.artist_service import ArtistService
from app.services.album_service import AlbumService
from app.services.track_service import TrackService

router = APIRouter(dependencies=ADMIN_DEPS)

@router.get('/getartistchars', response_model=ResponseModel[list[tuple[str, bool]]], tags=['edit'])
async def get_artist_chars(service: ArtistService = Depends(ArtistService)):
    start_chars = await service.get_artist_chars()
    return ResponseModel(data=start_chars)

@router.get('/getartists/{start_char}', response_model=ResponseModel[list[ArtistBase]], tags=['edit'])
async def get_artists(start_char: str, service: ArtistService = Depends(ArtistService)):
    artists = await service.get_start_char_artists(start_char)
    return ResponseModel(data=[ArtistBase.model_validate(a) for a in artists])

@router.get('/artist/{artist_id}', response_model=ResponseModel[ArtistResponse], tags=['edit'])
async def get_artist(artist_id: int, service: ArtistService = Depends(ArtistService)):
    artist = await service.get_artist(artist_id)
    if artist is None: 
        raise BusinessException(
            code=70104, 
            msg=f'artist not exists: {artist_id}',
            detail={'artist_id': artist_id},
            status_code=status.HTTP_404_NOT_FOUND
        )
    return ResponseModel(data=ArtistResponse.model_validate(artist))

@router.get('/album/{album_id}', response_model=ResponseModel[AlbumResponse], tags=['edit'])
async def get_album(album_id: int, service: AlbumService = Depends(AlbumService)):
    album = await service.get_album_with_track_detail(album_id)
    if not album:
        raise BusinessException(
            code=70204, 
            msg=f'album not exists: {album_id}', 
            detail={'album_id': album_id},
            status_code=status.HTTP_404_NOT_FOUND
        )
    return ResponseModel(data=AlbumResponse.model_validate(album))

@router.post('/uploadartistart', response_model=ResponseModel[ArtistArtUpdate], tags=['edit'])
async def upload_artist_art(item: ArtistArtCreate = Depends(artist_art_upload_from_form), service: ArtworkService = Depends(ArtworkService)):
    if item.file.content_type not in ['image/jpeg', 'image/png']:
        raise BusinessException(
            code=60115, 
            msg='only jpg and png files are allowed', 
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )
    try:
        await service.save_uploaded_artist_image(item.id, item.art_type, item.file)
        await item.file.close()
    except Exception as e:
        raise BusinessException(
            code=60106, 
            msg=f'failed to save artist art', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return ResponseModel(data=ArtistArtUpdate.model_validate({id: item.id, 'art_type': item.art_type}))

@router.post('/uploadalbumart', response_model=ResponseModel[CountResponse], tags=['edit'])
async def upload_album_art(item: AlbumArtCreate = Depends(album_art_upload_from_form), service: ArtworkService = Depends(ArtworkService)):
    if item.file.content_type not in ['image/jpeg', 'image/png']:
        raise BusinessException(
            code=60215, 
            msg='only jpg and png files are allowed', 
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )
    try:
        await service.save_uploaded_album_image(item.id, item.file)
        await item.file.close()
    except Exception as e:
        raise BusinessException(
            code=60207, 
            msg=f'failed to save album art', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return ResponseModel(data=CountResponse(count=item.id))

@router.post('/updatetrackfieldtag', response_model=ResponseModel[SuccessMsgModel], tags=['edit'])
async def update_track_field_tag(data: UpdateMetaTagList, service: TrackService = Depends(TrackService)):
    errors = await service.update_tracks_field_tag(data.items, data.field, data.value)
    if errors:
        errors_str = '\n  '.join([f"{item['track_path']}: {item['error']}" for item in errors])
        errors_paths = [item['track_path'] for item in errors]
        raise BusinessException(
            code=70316, 
            msg=f'update track metadata partial success: \n{errors_str}', 
            detail={'errors': errors_paths}, 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return ResponseModel(data=SuccessMsgModel())


# ============ Artist Art Candidate APIs ============

class SetArtistArtRequest(BaseModel):
    artist_id: int
    art_type: str
    filename: str


@router.get('/artistartcandidates/{artist_id}', response_model=ResponseModel[dict], tags=['edit'])
async def get_artist_art_candidates(
    artist_id: int,
    art_type: str,
    service: ArtworkService = Depends(ArtworkService)
):
    '''get candidate artwork filenames for an artist'''
    if art_type not in ('face', 'portrait'):
        raise BusinessException(
            code=60107, 
            msg='art_type must be face or portrait', 
            status_code=status.HTTP_400_BAD_REQUEST
        )
    try:
        candidates = await service.get_artist_art_candidates(artist_id, art_type)
    except ValueError as e:
        raise BusinessException(
            code=60108, 
            msg='candidate artist artwork not found', 
            status_code=status.HTTP_404_NOT_FOUND
        )
    return ResponseModel(data={'candidates': candidates})


@router.post('/uploadartistartcandidate', response_model=ResponseModel[dict], tags=['edit'])
async def upload_artist_art_candidate(
    file: UploadFile = File(...),
    artist_id: int = Form(...),
    art_type: str = Form(...),
    service: ArtworkService = Depends(ArtworkService)
):
    '''upload a candidate artwork image to the artist directory'''
    # validate file type
    if file.content_type not in ['image/jpeg', 'image/png']:
        raise BusinessException(
            code=60116, 
            msg='only jpg and png files are allowed', 
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )
    # validate file size (read and check)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise BusinessException(
            code=60113, 
            msg='file size exceeds 5MB limit', 
            detail={'file_limit': '5MB'}, 
            status_code=status.HTTP_413_CONTENT_TOO_LARGE
        )
    if art_type not in ('face', 'portrait'):
        raise BusinessException(
            code=60107, 
            msg='art_type must be face or portrait', 
            status_code=status.HTTP_400_BAD_REQUEST
        )
    try:
        filename = await service.upload_artist_art_candidate(artist_id, art_type, content)
    except ValueError as e:
        raise BusinessException(
            code=60109, 
            msg='failed to upload artist art candidate', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return ResponseModel(data={'filename': filename})


@router.post('/setartistart', response_model=ResponseModel[str], tags=['edit'])
async def set_artist_art(
    data: SetArtistArtRequest,
    service: ArtworkService = Depends(ArtworkService)
):
    '''set an artist\'s official artwork from a candidate file'''
    if data.art_type not in ('face', 'portrait'):
        raise BusinessException(
            code=60107, 
            msg='art_type must be face or portrait', 
            status_code=status.HTTP_400_BAD_REQUEST
        )
    try:
        url = await service.set_artist_art_from_candidate(data.artist_id, data.art_type, data.filename)
    except ValueError as e:
        raise BusinessException(
            code=60110, 
            msg='failed to set artist art from candidate', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return ResponseModel(data=url)