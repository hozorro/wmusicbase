from sqlalchemy import select
from sqlalchemy.orm import selectinload, load_only
from app.core.db import get_db
from app.models import Album, Track, Artist
from app.schemas.album import AlbumDetail

async def get_album(album_id: int): # OK
    async for db in get_db():
        stmt = (select(Album)
                .where(Album.id == album_id)
                .options(
                    selectinload(Album.album_artist).load_only(Artist.id, Artist.name, Artist.cover_art_hash),
                    selectinload(Album.tracks).options(
                        load_only(Track.id, Track.title, Track.cover_art_hash, Track.path),
                        selectinload(Track.artists).load_only(Artist.id, Artist.name, Artist.cover_art_hash),
                    )
                )
            )
        result = await db.execute(stmt)
        album = result.scalar_one_or_none()
        # if album:
        #     print(AlbumDetail.model_validate(album).model_dump_json(indent=4, ensure_ascii=False))
        return album

async def get_album_art(album_id: int):
    from app.services.artwork_service import ArtworkService
    from app.core.config import settings
    async for db in get_db():
        artwork_service = ArtworkService(db, settings)
        album = await get_album(album_id)
        album_dir = await artwork_service.get_album_directory(album)
        result = await artwork_service.find_album_cover_in_directory(album_dir)
        print(str(result))

if __name__ == '__main__':
    # import sys
    # if len(sys.argv) != 2: sys.exit(1)
    # arg = sys.argv[1]
    import asyncio
    asyncio.run(get_album_art(1761))