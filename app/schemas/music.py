# -*- encoding: utf-8 -*-
'''
@File      :   music.py
@Time      :   2025/11/01 22:59:17
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   music entity schemas
'''


from pydantic import BaseModel

class TrackBase(BaseModel):
    id: int
    title: str

class ArtistBase(BaseModel):
    id: int
    name: str