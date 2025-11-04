# -*- encoding: utf-8 -*-
'''
@File      :   sysinfo.py
@Time      :   2025/11/01 16:13:31
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   system information schemas
'''


from pydantic import BaseModel
from datetime import datetime
from .music import TrackBase, ArtistBase
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

class ScanInfo(BaseModel):
    is_running: bool
    progress: dict[str, int] | None = None

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
    scan_info: ScanInfo

class InitializedResponse(BaseModel):
    initialized: bool