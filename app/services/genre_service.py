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
from sqlalchemy.orm import selectinload, load_only, joinedload
from app.core.deps import SettingsDep, DbDep
from app.models import Genre, Track, Artist, Album, track_genres

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
        '''get all genres with track count'''
        track_count_subq = (
            select(
                track_genres.c.genre_id,
                func.count(Track.id).label('track_count')
            )
            .join(Track, Track.id == track_genres.c.track_id)
            .where(Track.is_deleted == False)
            .group_by(track_genres.c.genre_id)
            .subquery()
        )
        stmt = (
            select(
                Genre,
                func.coalesce(track_count_subq.c.track_count, 0).label('track_count')
            )
            .outerjoin(track_count_subq, Genre.id == track_count_subq.c.genre_id)
            .order_by(Genre.name)
        )
        result = await self.db.execute(stmt)
        genres = []
        for row in result:
            genre = row[0]
            genre.track_count = row.track_count
            genres.append(genre)
        return genres
    
    async def get_genre(self, genre_id: int) -> Genre | None:
        '''get genre by id with track count'''
        track_count_subq = (
            select(
                track_genres.c.genre_id,
                func.count(Track.id).label('track_count')
            )
            .join(Track, Track.id == track_genres.c.track_id)
            .where(Track.is_deleted == False)
            .group_by(track_genres.c.genre_id)
            .subquery()
        )
        stmt = (
            select(
                Genre,
                func.coalesce(track_count_subq.c.track_count, 0).label('track_count')
            )
            .outerjoin(track_count_subq, Genre.id == track_count_subq.c.genre_id)
            .where(Genre.id == genre_id)
        )
        result = await self.db.execute(stmt)
        row = result.first()
        if not row:
            return None
        genre = row[0]
        genre.track_count = row.track_count
        return genre
    
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
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.name),
                joinedload(Track.album).load_only(Album.title)
            )
            .join(track_genres, Track.id == track_genres.c.track_id)
            .where(track_genres.c.genre_id == genre_id)
            .offset(offset)
            .limit(page_size)
        )
        tracks = result.scalars().all()
        return total, tracks