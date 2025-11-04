# -*- encoding: utf-8 -*-
'''
@File      :   artists.py
@Time      :   2025/10/20 14:06:38
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router artists
'''


from fastapi import APIRouter, Depends
import logging

logger = logging.getLogger(__name__)
router = APIRouter()