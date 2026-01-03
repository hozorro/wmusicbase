# -*- encoding: utf-8 -*-
'''
@File      :   folder.py
@Time      :   2025/12/11 10:23:14
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   folder schemas
'''


from .common import FolderBase, TrackBase

class FolderResponse(FolderBase):  
    parent_id: int | None 
    children: list[FolderBase]
    tracks: list[TrackBase]
    