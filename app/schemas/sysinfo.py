# -*- encoding: utf-8 -*-
'''
@File      :   sysinfo.py
@Time      :   2025/11/01 16:13:31
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   system information schemas
'''


from pydantic import BaseModel, RootModel, ConfigDict, Field
from datetime import datetime
from .track import TrackBase
from .artist import ArtistBase
from typing import Literal

class ArtistStatInfo(ArtistBase):
    track_count: int

class TrackStatInfo(TrackBase):
    created_at: datetime

class EntityStats(BaseModel):
    track_count: int
    album_count: int
    artist_count: int
    folder_count: int
    genre_count: int
    playlist_count: int

class BasicStats(BaseModel):
    general: EntityStats
    artist_tracks_stats: list[ArtistStatInfo]
    latest_added_tracks_stats: list[TrackStatInfo]

class ArtistPlaybackStats(ArtistBase):
    play_count: int

class PlaybackStats(BaseModel):
    total_played: int
    recent_tracks: list[TrackBase]
    top_artists: list[ArtistPlaybackStats]

class WatcherInfo(BaseModel):
    is_running: bool
    watcher_path: str

class ScanFolder(BaseModel):
    path: str
    created_at: datetime
    last_update: datetime | None

class ScanInfo(BaseModel):
    is_scanning: bool
    scan_progress: dict[str, int | str] | None = None

class SysInfo(BaseModel):
    system: str
    python_version: str
    fastapi_version: str
    server_uptime: str

class DashboardInfo(BaseModel):
    system_status: Literal['ready', 'busy', 'error'] = 'ready'
    current_user: str | None = None
    basic_stats: BasicStats
    playback_stats: PlaybackStats
    system_info: SysInfo
    watcher_info: WatcherInfo

class InitializedResponse(BaseModel):
    initialized: bool

class LogProperty(BaseModel):
    log_types: list[dict[str, str]]
    log_levels: list[dict[str, str]]

class LogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    time: str
    level: str
    logger: str
    location: str
    message: str

class LogPageResponse(BaseModel):
    logs: list[LogResponse]
    pagination: dict[str, int]

# region frontend
class MetaItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_name: Literal['track', 'artist', 'album', 'folder', 'genre', 'playlist', 'trackhit', 'trackfav', 'artistfav', 'playlisthit']
    total_count: int = Field(0, ge=0, description='entity count')
    last_update: datetime | None = Field(None, description='last updated time')

class MusicStatInfo(RootModel):
    root: list[MetaItem]

class TransferRequest(BaseModel):
    page_num: int | None = 1
    page_size: int | None = 100
    last_sync: datetime | None = None

# endregion frontend

# region tools
class ArtistArtRequest(BaseModel):
    area: Literal['Chinese', 'Foreign']
    char_range: Literal['A-G', 'H-N', 'O-T', 'U-Z', 'Z_']

class ArtistArt(BaseModel):
    name: str
    covers: list[str]

class ArtistArtResponse(RootModel):
    root: list[ArtistArt]

class SetArtistArtsRequest(BaseModel):
    area: Literal['Chinese', 'Foreign']
    char_range: Literal['A-G', 'H-N', 'O-T', 'U-Z', 'Z_']
    covers: list[dict[str, str]]

class SetArtistArtsResponse(BaseModel):
    exists: list[str]
    created: list[str]
    no_dirs: list[str]
    total: int
