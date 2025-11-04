# -*- encoding: utf-8 -*-
'''
@File      :   __init__.py
@Time      :   2025/10/20 14:01:12
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   api v1 init
'''


from fastapi import APIRouter
from . import music, admin, auth, system

api_router = APIRouter()
api_router.include_router(music.music_router, prefix='/music', tags=['music'])
api_router.include_router(admin.admin_router, prefix='/admin', tags=['admin'])
api_router.include_router(auth.router, prefix='/auth', tags=['auth'])
api_router.include_router(system.router, prefix='/system', tags=['system'])