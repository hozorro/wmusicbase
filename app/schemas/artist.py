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


# ============ Artist Art Fetch from Third-party Search ============

class ArtistArtFetchRequest(BaseModel):
    '''fetch artist art from third-party search request'''
    artist_name: str = Field(..., min_length=1, description='Artist name to search')

class ArtistArtFetchResponse(BaseModel):
    '''fetch artist art response'''
    face_temp_id: str | None = Field(None, description='Temp ID for face image')
    portrait_temp_id: str | None = Field(None, description='Temp ID for portrait image')
    face_url: str | None = Field(None, description='Face image URL for preview')
    portrait_url: str | None = Field(None, description='Portrait image URL for preview')

class ArtistArtConfirmRequest(BaseModel):
    '''confirm artist art request'''
    artist_id: int = Field(..., description='Artist ID')
    art_type: str = Field(..., description='Art type: face or portrait')
    temp_id: str = Field(..., description='Temp ID from fetch response')
    set_directly: bool = Field(False, description='When True, immediately promote the saved image to the artist current artwork (position _1)')