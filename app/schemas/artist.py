# -*- encoding: utf-8 -*-
'''
@File      :   artist.py
@Time      :   2025/11/28 22:34:01
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   artist pydantic models
'''


from fastapi import UploadFile, Form, File
from pydantic import BaseModel, Field
from .common import ArtistBase, ArtistBrief, ArtistPrimary, AlbumBase, TrackBrief

class ArtistArtCreate(BaseModel):
    id: int
    art_type: str
    art: UploadFile
async def artist_art_upload_from_form(
    id: int = Form(..., description='Artist id'),
    art_type: str = Form(..., description='Art type'),
    art: UploadFile = File(...)
):
    return ArtistArtCreate(id=id, art_type=art_type, art=art)

class ArtistArtUpdate(BaseModel):
    id: int
    art_type: str

class ArtistResponse(ArtistBase):
    face_art_hash: str | None
    portrait_art_hash: str | None
    main_albums: list[AlbumBase]
    track_albums: list[AlbumBase]

class ArtistDetailResponse(ArtistBrief):
    main_albums: list[AlbumBase]
    track_albums: list[AlbumBase]
    top_tracks: list[TrackBrief]
    track_count: int

class OrphanArtistResponse(ArtistBase):
    '''orphan artist response'''
    pass

class OrphanArtistCleanupRequest(BaseModel):
    '''orphan artist cleanup request'''
    artist_ids: list[int] = Field(..., description='List of artist ids to cleanup')

class OrphanArtistCleanupResponse(BaseModel):
    '''orphan artist cleanup response'''
    deleted_count: int
    deleted_artists: list[ArtistPrimary]
    failed_ids: list[int] = []