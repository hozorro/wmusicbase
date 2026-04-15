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
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.db import engine
from app.core.exception_handlers import EXCEPTION_HANDLERS
from app.core.middleware import ScanMiddleware
from app.background.watcher_manager import watcher
from app.api.v1 import api_router
from app.core.logger import init_logging, logger

#========== Log configuration =======
init_logging()  # init logging, before other modules

#========== Life span ===============
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀Starting application...")
    logger.info("✅Server is ready to serve requests.")

    yield

    logger.info("🛑Shutting down...")
    ## Stop watcher
    if watcher.is_running(): 
        watcher.stop()

    await engine.dispose()
    logger.info("🛑Database connection closed.")
    logger.info("👋Application shutdown complete, Goodbye!")

app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

#========== CORS configuration ===========
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)
app.add_middleware(ScanMiddleware)
@app.middleware("http")
async def add_cors_to_fileresponse(request, call_next):
    response = await call_next(request)

    if isinstance(response, FileResponse):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Cache-Control"] = "no-store"
    
    return response

#=========== Including routers ===================
app.include_router(api_router, prefix="/api/v1")

#=========== Global exception handlers ===========
for exc_type, handler in EXCEPTION_HANDLERS:
    app.exception_handler(exc_type)(handler)
