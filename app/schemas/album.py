# -*- encoding: utf-8 -*-
'''
@File      :   album.py
@Time      :   2025/11/28 22:36:12
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   album pydantic models
'''


from fastapi import UploadFile
from pydantic import BaseModel, model_validator
from .common import AlbumBase, ArtistBase, TrackBrief
from .track import TrackDetail
from typing import Any

class AlbumArtUpload(BaseModel):
    id: int
    file: UploadFile

# album response
class AlbumResponse(AlbumBase):
    tracks: list[TrackDetail]

# region front
class AlbumDetail(AlbumBase):
    album_artist: ArtistBase
    artists: list[ArtistBase]
    tracks: list[TrackBrief]

    @model_validator(mode='before')
    @classmethod
    def artists(cls, data: Any) -> list[ArtistBase]:
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
        
    