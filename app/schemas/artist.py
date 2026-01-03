# -*- encoding: utf-8 -*-
'''
@File      :   artist.py
@Time      :   2025/11/28 22:34:01
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   artist pydantic models
'''


from fastapi import UploadFile
from pydantic import BaseModel,RootModel, Field
from .common import ArtistBase, ArtistBrief, AlbumBase, TrackBrief

class ArtistArtUpload(BaseModel):
    id: int
    art_type: str
    file: UploadFile

# response models
class ArtistsResponse(RootModel):
    root: list[ArtistBase] = Field(..., description='Artists array')
    
class StartCharsResponse(RootModel):
    root: list[tuple[str, bool]]

class ArtistBriefListResponse(RootModel):
    root: list[ArtistBrief]

class ArtistResponse(ArtistBase):
    main_albums: list[AlbumBase]
    track_albums: list[AlbumBase]

class ArtistDetailResponse(ArtistBrief):
    main_albums: list[AlbumBase]
    track_albums: list[AlbumBase]
    top_tracks: list[TrackBrief]
    track_count: int