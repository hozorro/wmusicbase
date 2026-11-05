# -*- encoding: utf-8 -*-
'''
@File      :   exceptions.py
@Time      :   2025/10/23 17:25:26
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   business exceptions
'''


from fastapi import status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


# HTTP 层错误统一映射到 10xxx 段：404/405 这类由框架抛出的异常也要带上业务码，
# 否则前端只能靠 status 分支，且响应体缺少 traceId。
# Map HTTP layer errors to 10xxx segment: 404/405 etc. that are thrown by the framework should add business code 
# otherwise the front end can only rely on the status branch, and the response body is missing traceId.
HTTP_STATUS_CODES = {
    status.HTTP_400_BAD_REQUEST: 10400,
    status.HTTP_401_UNAUTHORIZED: 10401,
    status.HTTP_403_FORBIDDEN: 10403,
    status.HTTP_404_NOT_FOUND: 10404,
    status.HTTP_405_METHOD_NOT_ALLOWED: 10405,
    status.HTTP_409_CONFLICT: 10409,
    status.HTTP_413_CONTENT_TOO_LARGE: 10413,
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: 10415,
    status.HTTP_416_RANGE_NOT_SATISFIABLE: 10416,
    status.HTTP_422_UNPROCESSABLE_CONTENT: 10422,
    status.HTTP_423_LOCKED: 10423,
    status.HTTP_429_TOO_MANY_REQUESTS: 10429,
    status.HTTP_500_INTERNAL_SERVER_ERROR: 10500,
    status.HTTP_502_BAD_GATEWAY: 10502,
    status.HTTP_503_SERVICE_UNAVAILABLE: 10503,
    status.HTTP_504_GATEWAY_TIMEOUT: 10504,
}


def http_code_of(status_code: int) -> int:
    '''map an http status to its 10xxx business code, unknown statuses fall back to 10500'''
    return HTTP_STATUS_CODES.get(status_code, 10500)


class BusinessException(Exception):
    '''
    business exception class
    - status_code is http status code
    - code is customized for business exception
    '''

    '''Customized business exception code, grouped by the first digit
    1xxxx: generic / framework (10404 not found, 10405 method not allowed, 10500 failed)
    2xxxx: auth and permission
    3xxxx: player (track / album / playlist / stream / netease / sync)
    6xxxx: artwork
    7xxxx: admin (edit / upload / scan / backup / lyric)
    '''
    def __init__(self, 
        code: int, 
        msg: str, 
        detail: dict | None = None, 
        status_code: int = 400
    ):
        self.code = code        # custom business exception code
        self.msg = msg          # diagnostic message, returned to the client as-is
        self.detail = detail    # structured parameters, or None
        self.status_code = status_code  # http status code

async def business_exception_handler(request: Request, exc: BusinessException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code, 
            "msg": exc.msg, 
            "detail": exc.detail,
            "traceId": getattr(request.state, "trace_id", None),
        },
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    fields = {}
    for error in exc.errors():
        loc = [str(x) for x in error['loc'] if x not in ('body', 'query', 'path')]
        field = '.'.join(loc) or 'general'
        fields.setdefault(field, []).append({
            'type': error.get('type', 'invalid'),
            'msg': error.get('msg'),
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "code": 10422, 
            "msg": "Validation error", 
            "detail": {'fields': fields}, 
            "traceId": getattr(request.state, "trace_id", None)
        },
    )

async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    '''unify every http level error (404 / 405 / 401 ...) into the same envelope

    starlette raises StarletteHTTPException for unknown routes and methods, so the
    handler is registered on that base class: the fastapi subclass is covered by mro.
    '''
    raw = getattr(exc, 'detail', None)
    if isinstance(raw, str) and raw:
        msg, detail = raw, None
    else:
        msg, detail = 'HTTP error', raw
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": http_code_of(exc.status_code),
            "msg": msg,
            "detail": detail,
            "traceId": getattr(request.state, "trace_id", None),
        },
        headers=getattr(exc, 'headers', None),
    )

async def unhandled_exception_handler(request: Request, exc: Exception):
    from app.core.logger import logger
    logger.exception('Unhandled exception: %s %s', request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": 10500, 
            "msg": "Internal Server Error", 
            "detail": None,
            "traceId": getattr(request.state, "trace_id", None)
        },
    )

EXCEPTION_HANDLERS = [
    (BusinessException, business_exception_handler),
    (RequestValidationError, validation_exception_handler),
    (StarletteHTTPException, http_exception_handler),
    (Exception, unhandled_exception_handler),
]