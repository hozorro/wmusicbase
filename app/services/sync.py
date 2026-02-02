# -*- encoding: utf-8 -*-
'''
@File      :   sync.py
@Time      :   2025/12/14 15:31:54
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   sync music data
'''


from datetime import datetime, timezone
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import Settings
from app.models import *

class Syncer:
    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings

    async def initialize_sync_meta(self):
        '''
        initialize sync meta when first start
        only writeable for backend, readonly for frontend
        '''
        # 1. base models
        for model in [Album, Artist, Folder, Genre, Track]:
            stmt = (select(
                func.coalesce(func.count(model.id).label('count'), 0),
                func.coalesce(func.max(model.updated_at).label('last_update'), datetime.now(tz=timezone.utc)),
            ))
            result = await self.db.execute(stmt)
            total_count, latest_time = result.one()
            
            meta = SyncMeta(model_name=model.__name__.lower(), last_update=latest_time, total_count=total_count)
            self.db.add(meta)

        # 2. playback
        all_users = (await self.db.execute(select(User.id))).scalars().all()
        if all_users:
            playbacks = {}
            # 3.1 playlist
            stmt = select(
                func.count(Playlist.id).label('count'),
                Playlist.user_id,
            ).where(Playlist.is_deleted == False).group_by(Playlist.user_id)
            result = await self.db.execute(stmt)
            playbacks['playlist'] = {user_id: count for count, user_id in result.all()}
            # 3.2 hit
            for model in [TrackHit, PlaylistHit]:
                stmt = select(
                    func.count(model.played_at).label('count'),
                    model.user_id,
                ).group_by(model.user_id)
                result = await self.db.execute(stmt)
                playbacks[model.__name__.lower()] = {user_id: count for count, user_id in result.all()}
            # 3.3 fav
            for model in [TrackFav, ArtistFav]:
                stmt = select(
                    func.count(model.favorited_at).label('count'),
                    model.user_id,
                ).group_by(model.user_id)
                result = await self.db.execute(stmt)
                playbacks[model.__name__.lower()] = {user_id: count for count, user_id in result.all()}

            latest_time = datetime.now(tz=timezone.utc)
            for user_id in all_users:
                for model_name, count in playbacks.items():
                    meta = (await self.db.execute(
                        select(SyncMeta).where(
                            SyncMeta.model_name == model_name, 
                            SyncMeta.user_id == user_id
                        )
                    )).scalar_one_or_none()
                    if meta:
                        meta.last_update = latest_time
                        meta.total_count = count.get(user_id, 0)
                    else:
                        meta = SyncMeta(model_name=model_name, last_update=latest_time, total_count=count.get(user_id, 0), user_id=user_id)
                        self.db.add(meta)
            
        await self.db.commit()

    async def update_basic_sync_meta(self, basic_model_name: str):
        model_map = {
            'track': Track,
            'album': Album,
            'artist': Artist,
            'folder': Folder,
            'genre': Genre,
        }
        model = model_map[basic_model_name]

        stmt = select(
            func.coalesce(func.max(model.updated_at), datetime.now(tz=timezone.utc)),
            func.coalesce(func.count(model.id), 0)
        )
        if basic_model_name == 'track':
            stmt = stmt.where(model.is_deleted == False)
        result = await self.db.execute(stmt)
        latest_time, total_count = result.one()

        result = await self.db.execute(select(SyncMeta).where(SyncMeta.model_name == basic_model_name))
        meta = result.scalar_one_or_none()
        if meta:
            meta.last_update = latest_time
            meta.total_count = total_count
        else:
            meta = SyncMeta(model_name=basic_model_name, last_update=latest_time, total_count=total_count)
            self.db.add(meta)
        
        await self.db.commit()

    async def update_playback_sync_meta(self, playback_model_name: str, user_id: int):
        model_map = {
            'trackhit': TrackHit,
            'playlisthit': PlaylistHit,
            'trackfav': TrackFav,
            'artistfav': ArtistFav,
            'playlist': Playlist
        }
        model = model_map[playback_model_name]

        latest_time = datetime.now(tz=timezone.utc)

        stmt = select(func.count(model.user_id))
        conditions = [model.user_id == user_id]
        if playback_model_name == 'playlist':
            conditions.append(model.is_deleted == False)
        stmt = stmt.where(and_(*conditions))
        total_count = await self.db.scalar(stmt) or 0

        meta = await self.db.scalar(select(SyncMeta).where(SyncMeta.model_name == playback_model_name, SyncMeta.user_id == user_id))
        if meta:
            meta.last_update = latest_time
            meta.total_count = total_count
        else:
            meta = SyncMeta(model_name=playback_model_name, last_update=latest_time, total_count=total_count, user_id=user_id)
            self.db.add(meta)
        
        await self.db.commit()