# -*- encoding: utf-8 -*-
'''
@File      :   genre.py
@Time      :   2025/10/18 22:09:45
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   genre model
'''


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import Track

from sqlalchemy import String, UniqueConstraint, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from . import Base, DateTimeMixin

class Genre(Base, DateTimeMixin):
    __tablename__ = 'genres'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    color: Mapped[str | None] = mapped_column(String(7)) # e.g. #FF0000
    info: Mapped[dict | None] = mapped_column(JSON)

    tracks: Mapped[list['Track']] = relationship(secondary='track_genres', back_populates='genres')

    __table_args__ = (UniqueConstraint('name', name='uq_genre_name'),)