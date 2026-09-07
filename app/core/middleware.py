# -*- encoding: utf-8 -*-
'''
@File      :   middleware.py
@Time      :   2025/10/26 10:25:56
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router middleware
'''


import uuid
from fastapi import Request, status
from starlette.responses import JSONResponse
from app.core.state import system_state
from starlette.middleware.base import BaseHTTPMiddleware

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
            response = JSONResponse(
                status_code=status.HTTP_423_LOCKED,
                content={'code': 423, 'msg': 'System is busy scanning music library, Please wait...'}
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)

class TraceIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = request.headers.get('X-Request-Id') or uuid.uuid4().hex
        request.state.trace_id = trace_id

        response = await call_next(request)
        response.headers['X-Request-Id'] = trace_id
        return response
