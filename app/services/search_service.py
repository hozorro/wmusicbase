# -*- encoding: utf-8 -*-
'''
@File      :   search_service.py
@Time      :   2025/06/23 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   search service for tracks, artists, albums
'''


from sqlalchemy import select, func
from sqlalchemy.orm import load_only, selectinload, joinedload
from app.core.deps import SettingsDep, DbDep
from app.models import Track, Artist, Album


class SearchService:
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    async def search(self, kw: str, limit: int = 20) -> dict:
        '''search tracks, artists, albums by keyword'''
        pattern = f'%{kw}%'

        # --- Albums ---
        track_count_subq = (
            select(
                Track.album_id,
                func.count(Track.id).label('track_count')
            )
            .where(Track.is_deleted == False)
            .group_by(Track.album_id)
            .subquery()
        )
        album_stmt = (
            select(
                Album,
                func.coalesce(track_count_subq.c.track_count, 0).label('track_count')
            )
            .outerjoin(track_count_subq, Album.id == track_count_subq.c.album_id)
            .where(Album.title.ilike(pattern))
            .order_by(Album.title)
            .limit(limit)
        )
        album_result = await self.db.execute(album_stmt)
        albums = []
        for row in album_result.all():
            album, count = row
            album.track_count = count
            albums.append(album)

        # --- Artists ---
        artist_stmt = (
            select(Artist)
            .where(Artist.name.ilike(pattern))
            .options(
                load_only(Artist.id, Artist.name, Artist.pinyin_initial,
                          Artist.face_art_hash, Artist.portrait_art_hash)
            )
            .order_by(Artist.name)
            .limit(limit)
        )
        artist_result = await self.db.execute(artist_stmt)
        artists = artist_result.scalars().all()

        # --- Tracks ---
        track_stmt = (
            select(Track)
            .where(Track.title.ilike(pattern), Track.is_deleted == False)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.name),
                joinedload(Track.album).load_only(Album.title),
            )
            .order_by(Track.title)
            .limit(limit)
        )
        track_result = await self.db.execute(track_stmt)
        tracks = track_result.scalars().all()

        return {
            'albums': albums,
            'artists': artists,
            'tracks': tracks,
        }
