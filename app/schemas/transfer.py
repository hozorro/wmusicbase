# -*- encoding: utf-8 -*-
'''
@File      :   transfer.py
@Time      :   2025/12/13 09:42:54
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   transfer schemas
'''


from datetime import datetime
from pydantic import BaseModel, RootModel, model_validator, Field
from .common import FolderBase, ArtistPrimary, ArtistBase, AlbumPrimary, AlbumBase, TrackBase, GenreBase, PlaylistPrimary
from typing import Any

class TransferRequest(BaseModel):
    last_sync: datetime | None = Field(datetime.min, description='Last sync time(ISO 8601 string)')
    page_num: int = Field(1, description='Page number, as the transfer batch numbe')
    page_size: int = Field(100, description='Page size, as the transfer batch size')

class TransferAlbum(AlbumBase):
    album_artist: ArtistPrimary
    artists: list[ArtistPrimary]

    @model_validator(mode='before')
    @classmethod
    def artists(cls, data: Any) -> list[ArtistPrimary]:
        artists_dict = {}
        if hasattr(data, 'tracks'):
            for track in data.tracks:
                for artist in track.artists:
                    artists_dict[artist.id] = artist
            data.artists = list(artists_dict.values())
        if isinstance(data, dict):
            if 'tracks' in data:
                for track in data['tracks']:
                    for artist in track['artists']:
                        artists_dict[artist['id']] = artist
            data['artists'] = list(artists_dict.values())
        return data

class TransferArtist(ArtistBase):
    pinyin_initial: str
    track_count: int

class TransferFolder(FolderBase):
    parent_id: int | None

class TransferGenre(GenreBase):
    info: dict | None

class TransferTrack(TrackBase):
    year: int | None
    album: AlbumPrimary
    artists: list[ArtistPrimary]
    duration: float | None
    genre_ids: list[int] | None
    folder_id: int
    updated_at: datetime
    is_deleted: bool | None

    @model_validator(mode='before')
    @classmethod
    def extract_models(cls, data: Any) -> dict[str, Any]:
        if hasattr(data, 'genres'):
            data.genre_ids = [genre.id for genre in data.genres]
        if isinstance(data, dict):
            if 'genres' in data:
                data['genre_ids'] = [genre['id'] for genre in data['genres']]
        return data

# region playback models
# region playback base models
class TransferHits(BaseModel):
    id: int
    played_ats: list[datetime]

class TransferArtistHitCounts(BaseModel):
    artist_id: int
    hit_count: int

class TransferFav(BaseModel):
    id: int
    favorited_at: datetime

    @model_validator(mode='before')
    @classmethod
    def unit_id(cls, data: Any) -> int:
        if hasattr(data, 'track_id'): 
            data.id = data.track_id
            delattr(data, 'track_id')
        if hasattr(data, 'artist_id'): 
            data.id = data.artist_id
            delattr(data, 'artist_id')
        if isinstance(data, dict):
            if 'track_id' in data:
                data['id'] = data['track_id']
                del data['track_id']
            if 'artist_id' in data:
                data['id'] = data['artist_id']
                del data['artist_id']
        return data

# endregion

# region playback upload and download response models
class TransferHitsList(RootModel):
    root: list[TransferHits]

class TransferArtistHitCountsList(RootModel):
    root: list[TransferArtistHitCounts]

class TransferFavsList(BaseModel):
    added: list[TransferFav]
    removed: list[TransferFav]

# endregion

# region playlist transfer model
class UploadPlaylist(BaseModel):
    id: int | None
    title: str
    comment: str | None
    is_deleted: bool | None
    track_ids: list[int]

class UploadPlaylists(RootModel):
    root: list[UploadPlaylist]

class UploadPlaylistsResponse(BaseModel):
    total: int
    created: int
    updated: int

class DownloadPlaylist(PlaylistPrimary):
    comment: str | None
    created_at: datetime
    updated_at: datetime
    is_deleted: bool
    track_ids: list[int]

    @model_validator(mode='before')
    @classmethod
    def extract_track_ids_and_hits(cls, data: Any) -> dict[str, Any]:
        if hasattr(data, 'tracks'):
            data.track_ids = [track.id for track in data.tracks]
        if isinstance(data, dict):
            if 'tracks' in data:
                data['track_ids'] = [track['track_id'] for track in data['tracks']]
        return data
    
# endregion

# endregion