from asyncache import cached
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, load_only
from app.core.db import get_db
from app.core.cache import ttl_cache
from app.models import Track, Genre, Artist, track_genres
from app.schemas.genre import GenresResponse, GenreTracksResponse

async def get_genres() -> list[Genre]:
    async for db in get_db():
        result = await db.execute(
            select(Genre).order_by(Genre.name)
        )
        genres = result.scalars().all()
        print(GenresResponse
            .model_validate(genres)
            .model_dump_json(indent=4, ensure_ascii=False)
        )

@cached(ttl_cache)
async def get_genre_tracks_total(genre_id: int) -> int:
    async for db in get_db():
        result = await db.execute(
            select(func.count(Track.id))
            .join(track_genres, Track.id == track_genres.c.track_id)
            .where(track_genres.c.genre_id == genre_id)
        )
        total = result.scalar_one()
        return total
async def get_paginated_tracks_of_genre(genre_id: int, page: int = 1, page_size: int = 5) -> tuple[int, list[Track]]:
    async for db in get_db():
        offset = (page - 1) * page_size
        
        total = await get_genre_tracks_total(genre_id)
        result = await db.execute(
            select(Track)
            .options(
                load_only(Track.id, Track.title),
                selectinload(Track.artists).load_only(Artist.name)
            )
            .join(track_genres, Track.id == track_genres.c.track_id)
            .where(track_genres.c.genre_id == genre_id)
            .offset(offset)
            .limit(page_size)
        )
        tracks = result.scalars().all()
        print(GenreTracksResponse
            .model_validate({'total': total, 'tracks': tracks})
            .model_dump_json(indent=4, ensure_ascii=False)
        )
if __name__ == '__main__':
    import asyncio
    asyncio.run(get_paginated_tracks_of_genre(5))
