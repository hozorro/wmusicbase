# -*- encoding: utf-8 -*-
'''
@File      :   folder.py
@Time      :   2025/10/18 21:52:05
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   folder model
'''


from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from . import Track

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from . import Base, DateTimeMixin

class Folder(Base, DateTimeMixin):
    __tablename__ = 'folders'

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str] = mapped_column(unique=True, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('folders.id'))
    
    parent: Mapped[Optional['Folder']] = relationship('Folder', remote_side=[id], back_populates='children')
    children: Mapped[list['Folder']] = relationship('Folder', back_populates='parent', order_by='Folder.path')
    tracks: Mapped[list['Track']] = relationship('Track', back_populates='folder', order_by='Track.title', cascade='all, delete-orphan')

    __table_args__ = (
        Index('ix_folders_path', 'path'),
        UniqueConstraint('path', name='uq_folder_path'),
    )