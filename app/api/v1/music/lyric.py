# -*- encoding: utf-8 -*-
'''
@File      :   lyric.py
@Time      :   2025/11/01 14:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router lyric: daily line
'''


from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.schemas.common import ResponseModel
from app.services.lyric_index_service import LyricIndexService

router = APIRouter()


class DailyLyric(BaseModel):
    lyric_id: int
    track_id: int
    best: str
    title: str
    artists: list[str]
    album: str | None = None
    cover_art_hash: str | None = None
    duration: float
    path: str


@router.get('/daily', response_model=ResponseModel[DailyLyric | None])
async def daily_lyric(service: LyricIndexService = Depends(LyricIndexService)):
    '''one random best line, the client keeps it for the whole day'''
    data = await service.daily_line()
    return ResponseModel(code=200, msg='ok', data=DailyLyric(**data) if data else None)
