# -*- encoding: utf-8 -*-
'''
@File      :   common.py
@Time      :   2025/10/23 17:42:05
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   common response struct
'''


from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, computed_field
from app.models.artist import Artist
from typing import TypeVar, Generic, Any

DataT = TypeVar('DataT')

class ResponseModel(BaseModel, Generic[DataT]):
    '''unified response structure'''
    model_config = ConfigDict(from_attributes=True)

    code: int = 200
    msg: str = 'ok'
    data: DataT | None = None

class ErrorResponseModel(BaseModel):
    '''unified error response structure(only used for docs, exceptions handled by exception handler acturally)'''
    code: int
    msg: str = 'error'
    detail: str | None = None

class SuccessMsgModel(BaseModel):
    '''unified success message structure for no exact data'''
    info: str = 'ok'

class CountResponse(BaseModel):
    '''unified count response structure'''
    count: int

# music entity base schemas, avoid circular imports
#==== Album ====
class AlbumPrimary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str

class AlbumBase(AlbumPrimary):
    cover_art_hash: str | None = None
    track_count: int = 0

#==== Artist ====
class ArtistPrimary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str

class ArtistBase(ArtistPrimary):
    face_art_hash: str | None = None
    portrait_art_hash: str | None = None

class ArtistBrief(ArtistBase):
    pinyin_initial: str

#==== Folder ====
class FolderBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    path: str = Field(..., exclude=True)

    @computed_field
    @property
    def name(self) ->  str:
        return Path(self.path).name
    
#===== Genre ====
class GenreBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str
    track_count: int = 0

#==== Playlist ====
class PlaylistPrimary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    cover_art_hash: str | None = None

class PlaylistBase(PlaylistPrimary):
    track_count: int = 0

#==== Track ====
class TrackPrimary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str

class TrackBase(TrackPrimary):
    cover_art_hash: str | None = None

class TrackBrief(TrackBase):
    duration: float
    album: str
    artists: list[str]  # artist_names list

    @field_validator('album', mode='before')
    @classmethod
    def extract_album_title(cls, v: Any) -> str:
        if v is None:
            return ''
        if hasattr(v, 'title'):
            return v.title
        return str(v)

    @field_validator('artists', mode='before')
    @classmethod
    def extract_names(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return [
                artist.name if isinstance(artist, Artist) else artist['name']
                for artist in v
            ]
        return []

class TrackMedium(TrackBase):
    duration: float
    artists: list[ArtistBase]


class MediaPath(BaseModel):
    name: str
    path: Path | str | None

    @field_validator('path')
    @classmethod
    def extract_path(cls, v: Path) -> str:
        if isinstance(v, Path):
            return f'{str('[app-base]' / v)}'
        return v
