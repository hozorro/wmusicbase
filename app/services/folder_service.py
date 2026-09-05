# -*- encoding: utf-8 -*-
'''
@File      :   folder_service.py
@Time      :   2025/12/09 13:09:31
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   folder service
'''


from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, joinedload, load_only
from app.core.deps import SettingsDep, DbDep
from app.models import Folder, Track, Album, Artist, SyncMeta
from app.schemas.sysinfo import ScanFolder

class FolderService:
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    async def get_folder(self, folder_id: int) -> Folder | None:
        '''get folder info, including ancestors, subfolders(with counts) and tracks'''
        stmt = (
            select(Folder)
            .where(Folder.id == folder_id)
            .options(
                selectinload(Folder.children).load_only(Folder.id, Folder.path, Folder.parent_id),
                selectinload(Folder.tracks).options(
                    load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                    joinedload(Track.album).load_only(Album.id, Album.title),
                    selectinload(Track.artists).load_only(Artist.id, Artist.name),
                ),
            )   
        )
        result = await self.db.execute(stmt)
        folder = result.scalars().first()
        if not folder: 
            return None

        # build ancestor chain (root -> ... -> parent, excluding self)
        ancestors = []
        current_parent_id = folder.parent_id
        while current_parent_id is not None:
            anc_result = await self.db.execute(
                select(Folder.id, Folder.path).where(Folder.id == current_parent_id)
            )
            row = anc_result.one_or_none()
            if row is None:
                break
            ancestors.append(row)
            # get parent_id of this ancestor
            pid_result = await self.db.execute(
                select(Folder.parent_id).where(Folder.id == row.id)
            )
            current_parent_id = pid_result.scalar_one_or_none()
        ancestors.reverse()
        folder.ancestors = ancestors

        # compute subfolder_count and track_count for each child
        child_ids = [c.id for c in folder.children]
        if child_ids:
            subfolder_counts = dict(
                (await self.db.execute(
                    select(Folder.parent_id, func.count(Folder.id))
                    .where(Folder.parent_id.in_(child_ids))
                    .group_by(Folder.parent_id)
                )).all()
            )
            track_counts = dict(
                (await self.db.execute(
                    select(Track.folder_id, func.count(Track.id))
                    .where(Track.folder_id.in_(child_ids), Track.is_deleted == False)
                    .group_by(Track.folder_id)
                )).all()
            )
        else:
            subfolder_counts = {}
            track_counts = {}

        subfolders = []
        for child in folder.children:
            child.subfolder_count = subfolder_counts.get(child.id, 0)
            child.track_count = track_counts.get(child.id, 0)
            subfolders.append(child)
        folder.subfolders = subfolders.sort(key=lambda x: x.path)

        return folder

    async def get_scan_folder(self) -> ScanFolder:
        result = await self.db.execute(select(Folder).where(Folder.parent_id == None))
        folder = result.scalar_one_or_none()
        if folder: 
            result_update = await self.db.execute(select(func.max(SyncMeta.last_update)).where(SyncMeta.user_id == None))
            folder_path = self.settings.MUSIC_LIBRARY_PATH / Path(folder.path)
            return ScanFolder(path=str(folder_path), created_at=folder.created_at, last_update=result_update.scalar_one_or_none())
        else:
            return ScanFolder(path=str(self.settings.MUSIC_LIBRARY_PATH), created_at=datetime.now(timezone.utc), last_update=None)
