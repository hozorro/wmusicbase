# -*- encoding: utf-8 -*-
'''
@File      :   genre.py
@Time      :   2025/11/28 22:36:54
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   genre pydantic models
'''


from pydantic import BaseModel
from app.schemas.common import GenreBase, TrackBrief

class GenreTracksResponse(BaseModel):
    total: int
    tracks: list[TrackBrief]