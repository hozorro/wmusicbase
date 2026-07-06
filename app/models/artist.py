# -*- encoding: utf-8 -*-
'''
@File      :   artist.py
@Time      :   2025/10/18 21:57:28
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   artist model
'''


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import Album, Track, ArtistFav

from sqlalchemy import String, UniqueConstraint, Index, JSON, CheckConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from . import Base, DateTimeMixin

class Artist(Base, DateTimeMixin):
    __tablename__ = 'artists'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(index=True)
    face_art_hash: Mapped[str | None] = mapped_column(String(40), index=True)
    portrait_art_hash: Mapped[str | None] = mapped_column(String(40), index=True)
    mb_artistid: Mapped[str | None] = mapped_column(index=True)
    info: Mapped[dict | None] = mapped_column(JSON)
    sort_name: Mapped[str] = mapped_column(index=True)
    pinyin_initial: Mapped[str] = mapped_column(String(1), index=True)

    # relations
    albums_as_main: Mapped[list['Album']] = relationship('Album', back_populates='album_artist')
    tracks: Mapped[list['Track']] = relationship(secondary='track_artists', back_populates='artists')
    favorites: Mapped[list['ArtistFav']] = relationship('ArtistFav', back_populates='artist', cascade='all, delete-orphan')

    __table_args__ = (
        UniqueConstraint('name', name='uq_artist_name'),
        Index('ix_artists_pinyin_initial', 'pinyin_initial'),
        Index('ix_artists_has_face', 'face_art_hash'),
        Index('ix_artists_has_portrait', 'portrait_art_hash'),
        CheckConstraint("pinyin_initial ~ '^[A-Z_]$'", name='chk_pinyin_initial') # for sqlite, regexp is not supported
    )
