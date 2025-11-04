# -*- encoding: utf-8 -*-
'''
@File      :   main.py
@Time      :   2025/10/20 14:33:22
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   fastapi entrance
'''


from contextlib import asynccontextmanager
# from sqlalchemy import text
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.db import engine
from app.core.exceptions import BusinessException
from app.core.middleware import ScanMiddleware
from app.models import Base
from app.api.v1 import api_router
# from app.background.watcher import start_watcher, stop_watcher
# from app.services.scanner import scan_music_library
from app.core.logger import setup_logging

#========== 配置日志 ===========
setup_logging()
import logging
logger = logging.getLogger(__name__)

#========== 生命周期 ===========
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀Starting application...")

    # 可选：首次启动时自动扫描（仅当Track表为空时）
    # async with engine.connect() as conn:
    #     result = await conn.execute(text("SELECT 1 FROM tracks LIMIT 1"))
    #     has_tracks = result.fetchone()

    # if not has_tracks:
    #     logger.info("🔍No Tracks found, Start initial scan...")
    #     async with engine.begin() as conn:
    #         await conn.run_sync(Base.metadata.create_all) # 确保表都存在
    #     await scan_music_library(settings.MUSIC_LIBRARY_PATH)
    #     logger.info("✅Initial scan completed.")
    
    # 启动文件监听
    # start_watcher()
    # logger.info("👀File watcher started.")

    yield

    logger.info("🛑Shutting down...")
    # 停止文件监听
    # await stop_watcher()
    # logger.info("🛑File watcher stopped.")
    await engine.dispose()
    logger.info("🛑Database connection closed.")
    logger.info("👋Application shutdown complete, Goodbye!")

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

#========== 配置跨域 ===========
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
)
app.add_middleware(ScanMiddleware)

#=========== 包含路由 ===========
app.include_router(api_router, prefix="/api/v1")

#=========== 全局异常处理 ===========
@app.exception_handler(BusinessException)
async def business_exception_handler(request: Request, exc: BusinessException):
    """业务异常处理"""
    return JSONResponse(
        status_code=400, 
        content={
            "code": exc.business_code, 
            "msg": exc.business_msg,
            "detail": exc.detail if settings.DEBUG else None
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP异常处理"""
    logger.error(f'HTTP exception: {exc}', exc_info=True)
    return JSONResponse(
        status_code=exc.status_code, 
        content={
            "code": exc.status_code, 
            "msg": exc.detail,
            "detail": exc.detail if settings.DEBUG else None
        }
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """未处理的异常处理"""
    logger.error(f'Unhandled exception: {exc}', exc_info=True)
    return JSONResponse(
        status_code=500, 
        content={
            "code": 500, 
            "msg": "Internal Server Error",
            "detail": str(exc) if settings.DEBUG else None
        }
    )