# -*- encoding: utf-8 -*-
'''
@File      :   genres.py
@Time      :   2025/10/20 14:07:28
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router genres
'''


from fastapi import APIRouter, Depends, Query, status
from app.core.exceptions import BusinessException
from app.schemas.common import ResponseModel, GenreBase, TrackBrief
from app.schemas.genre import GenreTracksResponse
from app.services.genre_service import GenreService

router = APIRouter()

def _genre_not_found(genre_id: int) -> BusinessException:
    '''build the unified 404 exception for a missing genre'''
    return BusinessException(
        code=30404, 
        msg=f'genre not exists: {genre_id}', 
        detail={'genre_id': genre_id},
        status_code=status.HTTP_404_NOT_FOUND
    )

@router.get('/randomgenres', response_model=ResponseModel[list[GenreBase]])
async def get_random_genres(service: GenreService = Depends(GenreService)):
    genres = await service.get_random_genres()
    return ResponseModel(data=[GenreBase.model_validate(g) for g in genres])

@router.get('/genres', response_model=ResponseModel[list[GenreBase]])
async def get_genres(service: GenreService = Depends(GenreService)):
    genres = await service.get_all_genres()
    return ResponseModel(data=[GenreBase.model_validate(g) for g in genres])

@router.get('/{genre_id}', response_model=ResponseModel[GenreBase])
async def get_genre(genre_id: int, service: GenreService = Depends(GenreService)):
    genre = await service.get_genre(genre_id)
    if not genre:
        raise _genre_not_found(genre_id)
    return ResponseModel(data=GenreBase.model_validate(genre))

@router.get('/{genre_id}/tracks', response_model=ResponseModel[GenreTracksResponse])
async def get_genre_tracks(
    genre_id: int, 
    page: int = Query(1, ge=1, description='page number'), 
    page_size: int = Query(20, ge=10, le=100, description='page size'), 
    service: GenreService = Depends(GenreService)
):
    result = await service.get_paginated_tracks_of_genre(genre_id, page, page_size)
    if result is None:
        raise _genre_not_found(genre_id)
    total, tracks = result
    # convert ORM tracks into the brief schema explicitly (same as other track endpoints)
    return ResponseModel(data=GenreTracksResponse(
        total=total, 
        tracks=[TrackBrief.model_validate(t) for t in tracks]
    ))