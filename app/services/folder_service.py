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
from sqlalchemy.orm import selectinload
from app.core.deps import SettingsDep, DbDep
from app.models import Folder, Track, SyncMeta
from app.schemas.sysinfo import ScanFolder

class FolderService:
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    async def get_folder(self, folder_id: int) -> Folder | None:
        '''get folder info, including sub_folder and tracks'''
        stmt = (
            select(Folder)
            .where(Folder.id == folder_id)
            .options(
                selectinload(Folder.children).load_only(Folder.id, Folder.path),
                selectinload(Folder.tracks).load_only(Track.id, Track.title, Track.cover_art_hash),
            )   
        )
        result = await self.db.execute(stmt)
        folder = result.scalars().first()
        if not folder: 
            return None
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
