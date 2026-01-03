# -*- encoding: utf-8 -*-
'''
@File      :   genre.py
@Time      :   2025/11/28 22:36:54
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   genre pydantic models
'''


from pydantic import BaseModel, RootModel, Field
from app.schemas.common import GenreBase, TrackBrief

class GenresResponse(RootModel):
    root: list[GenreBase] = Field(..., title='Genres')

class GenreTracksResponse(BaseModel):
    total: int
    tracks: list[TrackBrief]