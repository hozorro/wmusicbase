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
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.db import engine
from app.core.exceptions import EXCEPTION_HANDLERS
from app.core.middleware import ScanMiddleware, TraceIdMiddleware
from app.background.watcher_manager import watcher  # dev mode only; production uses supervisor
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
    # Stop watcher if running in dev mode (production uses supervisor)
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
@app.middleware("http")
async def add_cors_to_fileresponse(request, call_next):
    response = await call_next(request)

    if isinstance(response, FileResponse):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Cache-Control"] = "no-store"
    
    return response

app.add_middleware(ScanMiddleware)
app.add_middleware(TraceIdMiddleware)

#=========== Including routers ===================
app.include_router(api_router, prefix="/api/v1")
@app.get("/healthz")
def healthz():
    return {"status": "healthy"}

#=========== Static file serving (DEBUG only) ====
# In production, nginx serves these files directly from ARTWORK_DIR
if settings.DEBUG:
    app.mount('/media/artists', StaticFiles(directory=str(settings.ARTIST_ARTWORK_DIR)), name='media_artists')
    app.mount('/media/albums', StaticFiles(directory=str(settings.ALBUM_ARTWORK_DIR)), name='media_albums')
    app.mount('/media/tracks', StaticFiles(directory=str(settings.TRACK_ARTWORK_DIR)), name='media_tracks')
    app.mount('/media/playlists', StaticFiles(directory=str(settings.PLAYLIST_ARTWORK_DIR)), name='media_playlists')

#=========== Global exception handlers ===========
for exc_type, handler in EXCEPTION_HANDLERS:
    app.exception_handler(exc_type)(handler)
