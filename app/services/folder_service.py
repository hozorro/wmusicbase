# -*- encoding: utf-8 -*-
'''
@File      :   folder_service.py
@Time      :   2025/12/09 13:09:31
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   folder service
'''


from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.deps import SettingsDep, DbDep
from app.models.folder import Folder
from app.models.track import Track

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
                selectinload(Folder.tracks).load_only(Track.id, Track.title),
            )   
        )
        result = await self.db.execute(stmt)
        folder = result.scalars().first()
        if not folder: 
            return None
        return folder
        
        
        