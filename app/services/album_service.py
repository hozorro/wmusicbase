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
                    selectinload(Album.album_artist).load_only(Artist.id, Artist.name, Artist.cover_art_hash),
                    selectinload(Album.tracks).options(
                        load_only(Track.id, Track.title, Track.cover_art_hash),
                        selectinload(Track.artists).load_only(Artist.id, Artist.name),
                    )
                )
            )
        result = await self.db.execute(stmt)
        album = result.scalar_one_or_none()
        if not album: 
            return None

        return album
        