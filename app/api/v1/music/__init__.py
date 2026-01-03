# -*- encoding: utf-8 -*-
'''
@File      :   __init__.py
@Time      :   2025/10/25 10:39:23
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   music front end api
'''


from fastapi import APIRouter
from app.core.deps import COMMON_DEPS
from . import album, artist, folder, genre, track, playlist, transfer

music_router = APIRouter(dependencies=COMMON_DEPS)

music_router.include_router(album.router, prefix='/album', tags=['music_albums'])
music_router.include_router(artist.router, prefix='/artist', tags=['music_artists'])
music_router.include_router(folder.router, prefix='/folder', tags=['music_folders'])
music_router.include_router(genre.router, prefix='/genre', tags=['music_genres'])
music_router.include_router(track.router, prefix='/track', tags=['music_tracks'])
music_router.include_router(playlist.router, prefix='/playlist', tags=['music_playlists'])
music_router.include_router(transfer.router, prefix='/transfer', tags=['music_transfer'])