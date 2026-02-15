# -*- encoding: utf-8 -*-
'''
@File      :   __init__.py
@Time      :   2025/10/25 10:45:47
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   music back admin end api
'''


from fastapi import APIRouter
from . import scan, sysinfo, upload, edit, backup, log

admin_router = APIRouter()

admin_router.include_router(scan.router, prefix='/scan', tags=['admin_scan'])
admin_router.include_router(sysinfo.router, prefix='/sysinfo', tags=['admin_dashboard'])
admin_router.include_router(upload.router, prefix='/upload', tags=['admin_upload'])
admin_router.include_router(edit.router, prefix='/edit', tags=['admin_edit'])
admin_router.include_router(backup.router, prefix='/backup', tags=['admin_backup'])
admin_router.include_router(log.router, prefix='/log', tags=['admin_log'])