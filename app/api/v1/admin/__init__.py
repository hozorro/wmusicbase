# -*- encoding: utf-8 -*-
'''
@File      :   __init__.py
@Time      :   2025/10/25 10:45:47
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   music back admin end api
'''


from fastapi import APIRouter, Depends
from app.core.deps import require_admin
from . import scan, dashboard, upload

admin_router = APIRouter(dependencies=[Depends(require_admin)])

admin_router.include_router(scan.router, prefix='/scan', tags=['admin_scan'])
admin_router.include_router(dashboard.router, prefix='/dashboard', tags=['admin_dashboard'])
admin_router.include_router(upload.router, prefix='/upload', tags=['admin_upload'])