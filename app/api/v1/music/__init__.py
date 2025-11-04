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
from . import albums, artists, folders, genres, tracks, artwork

music_router = APIRouter()

music_router.include_router(albums.router, prefix='/album', tags=['music_albums'])
music_router.include_router(artists.router, prefix='/artist', tags=['music_artists'])
music_router.include_router(folders.router, prefix='/folder', tags=['music_folders'])
music_router.include_router(genres.router, prefix='/genre', tags=['music_genres'])
music_router.include_router(tracks.router, prefix='/track', tags=['music_tracks'])
music_router.include_router(artwork.router, prefix='/artwork', tags=['music_artwork'])