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
from pydantic import model_validator, BaseModel, RootModel, Field
from app.models.track import Track
from .common import TrackBase, TrackBrief, TrackMedium, AlbumBase

class TrackFavRequest(BaseModel):
    is_favorited: bool = Field(..., title='Is favorited')

class TrackBaseResponse(RootModel):
    root: list[TrackBase] = Field(..., title='Tracks')

class TrackBriefsResponse(RootModel):
    root: list[TrackBrief] = Field(..., title='Track Briefs')

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

class TrackFavResponse(RootModel):
    root: datetime | None = Field(None, title='Is Favorited')

class TrackDetail(TrackBase):
    artists: list[str]
    genres: list[str]
    path: str
    year: int | None

    @model_validator(mode='before')
    @classmethod
    def extract_names(cls, data: Track):
        if isinstance(data, Track):
            track_dict = {
                'id': data.id,
                'title': data.title,
                'artists': [artist.name for artist in data.artists],
                'genres': [genre.name for genre in data.genres],
                'path': data.path,
                'year': data.year
            }
            return cls.model_validate(track_dict)
        return data
    
class LyricResponse(RootModel):
    root: str | None = Field(None, title='Lyric')