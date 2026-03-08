# -*- encoding: utf-8 -*-
'''
@File      :   genre_service.py
@Time      :   2025/12/09 13:16:13
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   genre service
'''


from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, load_only
from app.core.deps import SettingsDep, DbDep
from app.models.genre import Genre
from app.models.track import Track, track_genres
from app.models.artist import Artist

class GenreService:
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    async def get_random_genres(self, limit: int = 8) -> list[Genre]:
        '''get random genres'''
        result = await self.db.execute(
            select(Genre).order_by(func.random()).limit(limit)
        )
        return result.scalars().all()
    
    async def get_all_genres(self) -> list[Genre]:
        '''get all genres'''
        result = await self.db.execute(
            select(Genre).order_by(Genre.name)
        )
        return result.scalars().all()
    
    async def get_genre(self, genre_id: int) -> Genre | None:
        '''get genre by id'''
        result = await self.db.execute(
            select(Genre).where(Genre.id == genre_id)
        )
        return result.scalar_one_or_none()
    
    async def get_paginated_tracks_of_genre(self, genre_id: int, page: int = 1, page_size: int = 20) -> tuple[int, list[Track]]:
        '''get paginated tracks of genre'''
        offset = (page - 1) * page_size
        total = await self.db.execute(
            select(func.count(Track.id))
            .join(track_genres, Track.id == track_genres.c.track_id)
            .where(track_genres.c.genre_id == genre_id)
        )
        total = total.scalar_one()
        result = await self.db.execute(
            select(Track)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash),
                selectinload(Track.artists).load_only(Artist.name)
            )
            .join(track_genres, Track.id == track_genres.c.track_id)
            .where(track_genres.c.genre_id == genre_id)
            .offset(offset)
            .limit(page_size)
        )
        tracks = result.scalars().all()
        return total, tracks