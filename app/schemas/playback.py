# -*- encoding: utf-8 -*-
'''
@File      :   playlist.py
@Time      :   2025/11/30 13:57:04
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   playlist schemas
'''

from fastapi import UploadFile, Form, File
from datetime import datetime
from pydantic import BaseModel, RootModel, Field, field_validator
from app.schemas.common import PlaylistBase, TrackBrief
from typing import Generic, TypeVar, Literal

class PlaylistCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description='Playlist title')
    comment: str | None = Field(None, max_length=255, description='Playlist comment')
    tracks: list[int] | None = Field(None, description='Tracks ids')
    cover: UploadFile | None
async def playlist_create_with_art_form(
    title: str = Form(..., min_length=1, max_length=100, description='Playlist title'),
    comment: str | None = Form(None, max_length=255, description='Playlist comment'),
    cover: UploadFile | None = File(None),
) -> PlaylistCreate:
    '''Playlist create with art upload depend'''
    return PlaylistCreate(title=title, comment=comment, cover=cover)

class PlaylistUpdate(BaseModel):
    id: int = Field(..., description='Playlist id')
    title: str | None = Field(None, min_length=1, max_length=100, description='Playlist title')
    comment: str | None = Field(None, max_length=255, description='Playlist comment')
    cover: UploadFile | None

async def playlist_update_with_art_form(
    id: int = Form(..., description='Playlist id'),
    title: str = Form(..., min_length=1, max_length=100, description='Playlist title'),
    comment: str | None = Form(None, max_length=255, description='Playlist comment'),
    cover: UploadFile | None = File(None),
) -> PlaylistCreate:
    '''Playlist create with art upload depend'''
    return PlaylistUpdate(id=id, title=title, comment=comment, cover=cover)

class TrackToPlaylistRequest(BaseModel):
    track_id: int = Field(..., description='Track id')
    playlist_id: int = Field(..., description='Playlist id')

class PlaylistDeleteRequest(BaseModel):
    id: int = Field(..., description='Playlist id')

class MovePlaylistTrackRequest(BaseModel):
    id: int = Field(..., description='Playlist id')
    track_id: int = Field(..., description='Track id to move')
    new_position: int = Field(..., ge=0, description='Target position in playlist (0-based)')

# ============ Hit & Fav request schemas ============
class TrackHitRequest(BaseModel):
    track_id: int = Field(..., description='Track id')

class ArtistHitRequest(BaseModel):
    artist_id: int = Field(..., description='Artist id')

class PlaylistHitRequest(BaseModel):
    playlist_id: int = Field(..., description='Playlist id')

class TrackFavRequest(BaseModel):
    track_id: int = Field(..., description='Track id')
    is_favorited: bool = Field(..., description='True to favorite, False to unfavorite')

class ArtistFavRequest(BaseModel):
    artist_id: int = Field(..., description='Artist id')
    is_favorited: bool = Field(..., description='True to favorite, False to unfavorite')

class PlaylistImport(BaseModel):
    id: int | None = Field(None, description='Playlist id, only used for update')
    title: str = Field(..., description='Playlist title', min_length=1, max_length=100)
    comment: str | None = Field(None, description='Playlist comment', max_length=255)
    tracks: list[str] | None = Field(None, description='Tracks', min_length=1, max_length=200)

    @field_validator('tracks')
    @classmethod
    def validate_tracks(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for track in v:
            if not track.startswith('Chinese') and not track.startswith('Foreign'):
                raise ValueError('Track path must be relative to music library root')
        return v

class PlaylistImportRoot(RootModel):
    root: list[PlaylistImport] = Field(..., description='Playlists array')

    @field_validator('root')
    @classmethod
    def validate_root(cls, v: list[PlaylistImport]) -> list[PlaylistImport]:
        if len(v) == 0:
            raise ValueError('Playlists array is empty')
        if len(v) > 50: # 50 playlists limited, setting.................
            raise ValueError(f'50 playlists import at once, current playlists count: {len(v)}.')
        return v
    
class PlaylistResponse(PlaylistBase):
    comment: str | None = None
    created_at: datetime

class PlaylistTrackBrief(TrackBrief):
    position: int = 0

class PlaylistWithTracksResponse(PlaylistResponse):
    tracks: list[PlaylistTrackBrief] | None = None

# ============ Hit & Fav & Playlist import schemas ============
T = TypeVar('T', bound=datetime)
class OperationImport(BaseModel, Generic[T]):
    track: str = Field(..., description='track path')

    @classmethod
    def _validate_time_field(cls, v: str) -> T:
        '''union time field validator'''
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            raise ValueError(f'Invalid ISO 8601 string: {v}, should be like 2023-01-01T00:00:00(.000+08:00)')

    @field_validator('track')
    @classmethod
    def validate_path(cls, v):
        if not v.startswith('Chinese') and not v.startswith('Foreign'):
            raise ValueError('Path is relative to music library root')
        return v
    
class HitImport(OperationImport[datetime]):
    '''hit record import model'''
    played_at: str = Field(..., description='Play time(ISO 8601 string)')

    @field_validator('played_at')
    @classmethod
    def validate_played_at(cls, v: str) -> datetime:
        return cls._validate_time_field(v)
    
class FavImport(OperationImport[datetime]):
    '''favorite record import model'''
    favorited_at: str = Field(..., description='Favorite time(ISO 8601 string)')

    @field_validator('favorited_at')
    @classmethod
    def validate_favorited_at(cls, v: str) -> datetime:
        return cls._validate_time_field(v)
        
U = TypeVar('U', HitImport, FavImport)

class OperationImportRoot(RootModel[U]):
    '''operations import root model'''
    root: list[U] = Field(..., description='Operations array')

    @field_validator('root')
    @classmethod
    def validate_root(cls, v: list[U]) -> list[U]:
        if len(v) == 0:
            raise ValueError('Operations array is empty')
        if len(v) > 10000: # 10000 operations limited, setting..............
            raise ValueError(f'10000 operations import at once, current operations count: {len(v)}.')
        return v
    
class HitImportRoot(OperationImportRoot[HitImport]):
    '''hit record import root model'''
    pass

class FavImportRoot(OperationImportRoot[FavImport]):
    '''favorite record import root model'''
    pass
    
class ImportJsonUpload(BaseModel):
    user_id: int = Field(..., description='User id')
    file: UploadFile
    
class PlaylistJsonUpload(ImportJsonUpload):
    mode: Literal['merge', 'replace', 'skip'] = Field('merge', description='Update playlist mode if exists')

class JsonImportResponse(BaseModel):
    total: int = Field(0, description='Total playlists')
    success: int = Field(0, description='Success playlists')
    skipped: int = Field(0, description='Skipped playlists')
    failed: int = Field(0, description='Failed playlists')
    errors: list[str] = Field([], description='Error messages')


