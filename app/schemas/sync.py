# -*- encoding: utf-8 -*-
'''
@File      :   sync.py
@Time      :   2026/08/06 10:00:00
@Author    :   enauvy
@Version   :   2.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   sync schemas for frontend indexeddb incremental sync
'''


from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


StoreName = Literal['tracks', 'albums', 'artists', 'genres', 'folders', 'playlists']


class SyncArtistRef(BaseModel):
    '''artist reference embedded in tracks / albums'''
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class SyncAlbumRef(BaseModel):
    '''album reference embedded in tracks'''
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str


class SyncTrack(BaseModel):
    '''track entity shape for frontend sync (RawTrack)'''
    id: int
    title: str
    artists: list[SyncArtistRef] = []
    album: SyncAlbumRef | None = None
    duration: float
    cover_art_hash: str | None = None
    year: int | None = None
    genre_ids: list[int] = []
    folder_id: int
    created_at: datetime | None = None
    # playback fields: backend authoritative, delivered with sync
    favorited_at: datetime | None = None
    hits: list[datetime] | None = None


class SyncArtist(BaseModel):
    '''artist entity shape for frontend sync (RawArtist)'''
    id: int
    name: str
    pinyin_initial: str
    face_art_hash: str | None = None
    portrait_art_hash: str | None = None
    track_count: int = 0
    favorited_at: datetime | None = None
    hit_count: int | None = None


class SyncAlbum(BaseModel):
    '''album entity shape for frontend sync (RawAlbum)'''
    id: int
    title: str
    album_artist: SyncArtistRef | None = None
    artists: list[SyncArtistRef] = []
    cover_art_hash: str | None = None
    track_count: int = 0


class SyncGenre(BaseModel):
    '''genre entity shape for frontend sync (RawGenre)'''
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color: str | None = None


class SyncFolder(BaseModel):
    '''folder entity shape for frontend sync (RawFolder)'''
    id: int
    name: str
    parent_id: int | None = None

    @classmethod
    def from_model(cls, folder: Any) -> 'SyncFolder':
        return cls(id=folder.id, name=Path(folder.path).name, parent_id=folder.parent_id)


class SyncPlaylistTrackRef(BaseModel):
    '''playlist track reference with position'''
    id: int
    position: int


class SyncPlaylist(BaseModel):
    '''playlist entity shape for frontend sync (RawPlaylist)'''
    id: int
    title: str
    comment: str | None = None
    cover_art_hash: str | None = None
    created_at: datetime
    tracks: list[SyncPlaylistTrackRef] = []
    hit_count: int | None = None


SyncItem = SyncTrack | SyncArtist | SyncAlbum | SyncGenre | SyncFolder | SyncPlaylist


class SyncPullResponse(BaseModel):
    '''response data of GET /music/sync/pull'''
    items: list[SyncItem]
    next_after_id: int | None = None


class SyncSummary(BaseModel):
    '''response data of GET /music/sync/summary'''
    counts: dict[str, int]
    # deleted ids per store, only carried for incremental sync (since given)
    deleted: dict[str, list[int]] | None = None
    serverTime: datetime = Field(alias='serverTime')

    model_config = ConfigDict(populate_by_name=True)
