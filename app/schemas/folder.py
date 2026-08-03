# -*- encoding: utf-8 -*-
'''
@File      :   folder.py
@Time      :   2025/12/11 10:23:14
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   folder schemas
'''


from .common import FolderBase, TrackBrief

class FolderBrief(FolderBase):
    subfolder_count: int = 0
    track_count: int = 0

class FolderResponse(FolderBase):
    ancestors: list[FolderBase] = []
    subfolders: list[FolderBrief] = []
    tracks: list[TrackBrief] = []
    