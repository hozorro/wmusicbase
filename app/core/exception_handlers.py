# -*- encoding: utf-8 -*-
'''
@File      :   exception_handlers.py
@Time      :   2025/12/01 14:52:45
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   exception handlers
'''


from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
from app.core.logger import logger
from app.core.exceptions import BusinessException

async def business_exception_handler(request: Request, exc: BusinessException) -> JSONResponse:
    '''business exception handler'''
    logger.warning(f"business exception from {request.url}: {exc.business_code} {exc.business_msg} {exc.detail}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST, 
        content={
            "code": exc.business_code, 
            "msg": exc.business_msg,
            "detail": exc.detail if settings.DEBUG else None
        }
    )

async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP exception handler"""
    logger.error(f'HTTP exception from {request.url}: {exc}')
    return JSONResponse(
        status_code=exc.status_code, 
        content={
            "code": exc.status_code, 
            "msg": exc.detail,
            "detail": exc.detail if settings.DEBUG else None
        }
    )

async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """SQLAlchemy exception handler"""
    logger.error(f'SQLAlchemy exception from {request.url}: {str(exc)}', exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        content={
            "code": status.HTTP_500_INTERNAL_SERVER_ERROR, 
            "msg": "Database operation error",
            "detail": str(exc) if settings.DEBUG else None
        }
    )

async def unhandled_exception_handler(request: Request, exc: Exception):
    """unhandled exception handler"""
    logger.error(f'Unhandled exception from {request.url}: {exc}', exc_info=True)
    return JSONResponse(
        status_code=500, 
        content={
            "code": 500, 
            "msg": "Internal Server Error",
            "detail": str(exc) if settings.DEBUG else None
        }
    )

EXCEPTION_HANDLERS = [
    (BusinessException, business_exception_handler),
    (SQLAlchemyError, sqlalchemy_exception_handler),
    (HTTPException, http_exception_handler),
    (Exception, unhandled_exception_handler)
]