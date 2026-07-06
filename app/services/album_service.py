# -*- encoding: utf-8 -*-
'''
@File      :   album_service.py
@Time      :   2025/11/29 20:12:12
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   album service
'''


from sqlalchemy.orm import selectinload, load_only
from sqlalchemy import select
from app.core.deps import SettingsDep, DbDep
from app.models.album import Album
from app.models.track import Track
from app.models.artist import Artist

class AlbumService:
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.settings = settings
        self.db = db

    async def get_album(self, album_id: int) -> Album | None:
        '''get album info, preload album_artist and tracks'''
        stmt = (select(Album)
                .where(Album.id == album_id)
                .options(
                    selectinload(Album.album_artist).load_only(Artist.id, Artist.name, Artist.face_art_hash, Artist.portrait_art_hash),
                    selectinload(Album.tracks).options(
                        load_only(Track.id, Track.title, Track.cover_art_hash),
                        selectinload(Track.artists).load_only(Artist.id, Artist.name, Artist.face_art_hash, Artist.portrait_art_hash),
                    )
                )
            )
        result = await self.db.execute(stmt)
        album = result.scalar_one_or_none()
        if not album: 
            return None

        return album
    
    async def get_album_with_track_detail(self, album_id: int) -> dict | None:
        '''获取指定专辑的基本信息和所有歌曲的详细信息（含歌曲artists和genres）'''
        stmt = (
            select(Album)
            .where(Album.id == album_id)
            .options(
                # 预加载tracks
                selectinload(Album.tracks).options(
                    # 预加载每个track的artists和genres
                    selectinload(Track.artists),
                    selectinload(Track.genres)
                )
            )
        )
        result = await self.db.execute(stmt)
        album = result.scalar_one_or_none()
        if not album:
            return None
        return album
        