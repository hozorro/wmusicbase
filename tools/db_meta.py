from datetime import datetime, timezone
from sqlalchemy import select, func
from fastapi import Depends
from app.models import SyncMeta, Track
from app.core.db import get_db, engine
from app.services.sync import Syncer

async def gen_model_meta():
    async for db in get_db():
        result = await db.execute(
            select(
                func.coalesce(func.max(Track.updated_at), datetime.now(tz=timezone.utc)),
                func.coalesce(func.count(Track.id), 0)
            ).where(Track.is_deleted == False)
        )
        track_updated_at, track_count = result.one()
        print(f'Track meta: {track_updated_at}, {track_count}')

async def get_meta_updated_at():
    async for db in get_db():
        result = await db.execute(select(func.max(SyncMeta.last_update)).where(SyncMeta.user_id == None))

        last_update = result.scalar_one_or_none()
        print(f'last_update: {last_update}')


async def drop_table():
    async with engine.begin() as conn:
        await conn.run_sync(SyncMeta.__table__.drop)

async def create_table():
    async with engine.begin() as conn:
        await conn.run_sync(SyncMeta.__table__.create)

async def update_basic_meta():
    from app.core.config import settings
    async for db in get_db():
        syncer = Syncer(db, settings)
        for model in ['album', 'artist', 'folder', 'genre', 'track']:
            await syncer.update_basic_sync_meta(model)

if __name__ == '__main__':
    import asyncio
    asyncio.run(update_basic_meta())
