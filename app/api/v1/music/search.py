# -*- encoding: utf-8 -*-
'''
@File      :   search.py
@Time      :   2025/06/23 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router search
'''


from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from app.schemas.common import ResponseModel, AlbumBase, ArtistBrief, TrackBrief
from app.services.search_service import SearchService

router = APIRouter()


class SearchResult(BaseModel):
    albums: list[AlbumBase]
    artists: list[ArtistBrief]
    tracks: list[TrackBrief]


@router.get('', response_model=ResponseModel[SearchResult])
async def search(
    kw: str = Query(..., min_length=1, description='Search keyword'),
    limit: int = Query(20, ge=1, le=50, description='Max results per category'),
    service: SearchService = Depends(SearchService),
):
    result = await service.search(kw, limit)
    return ResponseModel(data=SearchResult(
        albums=[AlbumBase.model_validate(a) for a in result['albums']],
        artists=[ArtistBrief.model_validate(a) for a in result['artists']],
        tracks=[TrackBrief.model_validate(t) for t in result['tracks']],
    ))
