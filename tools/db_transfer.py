from datetime import datetime, timezone
from sqlalchemy import func, select
from fastapi import Request
from app.core.db import get_db
from app.core.config import settings
from app.models import User, Album
from app.services.transfer_service import TransferService
from app.schemas.transfer import (
    TransferAlbumListResponse, TransferArtistListResponse, TransferFolderListResponse, 
    TransferGenreListResponse, TransferTrackListResponse, DownloadPlaylistListsResponse
)

request = Request(scope={'type': 'http'})
request.state.user = User(id=1)
last_sync = datetime.fromisoformat('2000-01-01T00:00:00Z')

async def test_transfer_album_service():
    async for db in get_db():
        service = TransferService(db, settings=settings, request=request)
        result = await service.transfer_albums(last_sync=last_sync, page_size=10)
        print(TransferAlbumListResponse.model_validate(result).model_dump_json(indent=4, ensure_ascii=False))

async def test_transfer_artist_service():
    async for db in get_db():
        service = TransferService(db, settings=settings, request=request)
        result = await service.transfer_artists(last_sync=last_sync, page_num=3, page_size=500)
        # print(TransferArtistListResponse.model_validate(result).model_dump_json(indent=4, ensure_ascii=False))
        print(len(result))


async def test_transfer_folder_service():
    async for db in get_db():
        service = TransferService(db, settings=settings, request=request)
        result = await service.transfer_folders(last_sync=last_sync, page_size=10)
        print(TransferFolderListResponse.model_validate(result).model_dump_json(indent=4, ensure_ascii=False))

async def test_transfer_genre_service():
    async for db in get_db():
        service = TransferService(db, settings=settings, request=request)
        result = await service.transfer_genres(last_sync=last_sync, page_size=10)
        print(TransferGenreListResponse.model_validate(result).model_dump_json(indent=4, ensure_ascii=False))

async def test_transfer_playlist_service():
    async for db in get_db():
        service = TransferService(db, settings=settings, request=request)
        result = await service.transfer_playlists(last_sync=last_sync, page_size=10)
        print(DownloadPlaylistListsResponse.model_validate(result).model_dump_json(indent=4, ensure_ascii=False))

async def test_transfer_track_service():
    async for db in get_db():
        service = TransferService(db, settings=settings, request=request)
        result = await service.transfer_tracks(last_sync=last_sync, page_size=10)
        print(TransferTrackListResponse.model_validate(result).model_dump_json(indent=4, ensure_ascii=False))

async def test_init():
    async for db in get_db():
        stmt = (select(
            func.coalesce(func.count(Album.id).label('count'), 0),
            func.coalesce(func.max(Album.updated_at).label('last_update'), datetime.now(tz=timezone.utc)),
        ))
        result = await db.execute(stmt)
        total_count, lastest_time = result.one()
        print(total_count, lastest_time)


if __name__ == '__main__':
    import asyncio
    asyncio.run(test_transfer_artist_service())
