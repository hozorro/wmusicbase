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
from app.services.lyric_index_service import LyricIndexService

router = APIRouter()


class SearchResult(BaseModel):
    albums: list[AlbumBase]
    artists: list[ArtistBrief]
    tracks: list[TrackBrief]


class LyricSnippet(BaseModel):
    text: str
    highlights: list[list[int]]


class LyricSearchItem(BaseModel):
    lyric_id: int
    track_id: int
    title: str
    artists: list[str]
    album: str | None = None
    album_id: int | None = None
    cover_art_hash: str | None = None
    duration: float
    snippets: list[LyricSnippet]


class LyricSearchResult(BaseModel):
    total: int
    items: list[LyricSearchItem]


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


@router.get('/lyric', response_model=ResponseModel[LyricSearchResult])
async def search_lyric(
    kw: str = Query(..., min_length=1, description='Lyric keyword'),
    limit: int = Query(20, ge=1, le=50, description='Max results per page'),
    offset: int = Query(0, ge=0, description='Page offset'),
    service: LyricIndexService = Depends(LyricIndexService),
):
    '''full text search over lyrics, snippets highlight every hit of the keyword'''
    total, items = await service.search(kw, limit, offset)
    return ResponseModel(data=LyricSearchResult(
        total=total,
        items=[LyricSearchItem(**item) for item in items],
    ))
