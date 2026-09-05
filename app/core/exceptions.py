# -*- encoding: utf-8 -*-
'''
@File      :   exceptions.py
@Time      :   2025/10/23 17:25:26
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   business exceptions
'''


from fastapi import HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError


class BusinessException(Exception):
    '''
    business exception class
    - status_code is http status code
    - code is customized for business exception
    '''

    '''Customized business exception code
    10203: partial success
    10404: resource not found
    10405: resource already exists
    10406: resource not allowed
    10500: operation failed
    to be continued
    '''
    def __init__(self, 
        code: int, 
        msg: str, 
        detail: dict | None = None, 
        status_code: int = 400
    ):
        self.code = code        # custom business exception code
        self.msg = msg          # only for backend, not exposed to frontend
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

async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": 10500, 
            "msg": "Internal Server Error", 
            "detail": None,
            "traceId": getattr(request.state, "trace_id", None)
        },
    )

async def unhandled_exception_handler(request: Request, exc: Exception):
    from app.core.logger import logger
    logger.exception('Unhandled exception: %s %s', request.method, request.url.path)
    return JSONResponse(
        status_code=500,
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
    (HTTPException, http_exception_handler),
    (Exception, unhandled_exception_handler),
]