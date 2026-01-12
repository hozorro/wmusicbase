# -*- encoding: utf-8 -*-
'''
@File      :   album.py
@Time      :   2025/10/18 22:03:05
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   album model
'''


from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from . import Artist, Track

from sqlalchemy import ForeignKey, UniqueConstraint, String, Index
from sqlalchemy.orm import relationship, Mapped, mapped_column
from . import Base, DateTimeMixin

class Album(Base, DateTimeMixin):
    __tablename__ = 'albums'

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    year: Mapped[int | None]
    cover_art_hash: Mapped[str | None] = mapped_column(String(40), index=True)
    mb_albumid: Mapped[str | None] = mapped_column(index=True)
    album_artist_id: Mapped[int | None] = mapped_column(ForeignKey('artists.id', ondelete='SET NULL'))

    album_artist: Mapped[Optional['Artist']] = relationship('Artist', back_populates='albums_as_main')
    tracks: Mapped[list['Track']] = relationship('Track', back_populates='album')

    __table_args__ = (
        Index('ix_albums_has_cover', 'cover_art_hash'),
        UniqueConstraint('title', 'album_artist_id', name='uq_album_title_artist'),
    )