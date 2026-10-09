# -*- encoding: utf-8 -*-
'''
@File      :   track.py
@Time      :   2025/11/28 22:31:51
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   track pydantic models
'''


from datetime import datetime
from typing import Any
from pydantic import model_validator
from app.models.track import Track
from .common import TrackBase, TrackMedium, AlbumBase

class TrackInfoResponse(TrackMedium):
    album: AlbumBase
    hit_count: int
    favorited_at: datetime | None = None

class TrackMoreInfoResponse(TrackBase):
    duration: float | None
    bitrate: int | None
    bitrate_mode: str | None
    year: int | None
    acoustid_id: str | None
    mb_trackid: str | None
    path: str
    created_at: datetime

class TrackDetail(TrackBase):
    artists: list[str]
    genres: list[str]
    path: str
    year: int | None

    @model_validator(mode='before')
    @classmethod
    def extract_names(cls, data: Any) -> Any:
        if isinstance(data, Track):
            return {
                'id': data.id,
                'title': data.title,
                'cover_art_hash': data.cover_art_hash,
                'artists': [artist.name for artist in data.artists],
                'genres': [genre.name for genre in data.genres],
                'path': data.path,
                'year': data.year
            }
        return data