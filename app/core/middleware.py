# -*- encoding: utf-8 -*-
'''
@File      :   middleware.py
@Time      :   2025/10/26 10:25:56
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router middleware
'''


from fastapi import Request, status, HTTPException
from app.core.state import system_state

ALLOWED_DURING_SCAN = {
    '/api/v1/system/initialized',
    '/api/v1/auth/login',
    '/api/v1/auth/refresh',
    '/api/v1/auth/register',
    '/api/v1/admin/upload',
    '/api/v1/admin/dashboard/stats',
    '/api/v1/admin/scan/progress',
    '/api/v1/admin/scan/cancel',
}

class ScanMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        
        request = Request(scope)
        if system_state.is_scanning and request.url.path not in ALLOWED_DURING_SCAN:
            # return 423 Locked（resource is currently locked）
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED, 
                detail='System is busy scanning music library, Please wait...'
            )
        await self.app(scope, receive, send)
