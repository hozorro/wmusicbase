# -*- encoding: utf-8 -*-
'''
@File      :   user.py
@Time      :   2025/10/18 22:21:59
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   user model
'''


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import TrackHit, TrackFav, ArtistFav, Playlist, PlaylistHit, SyncMeta

from sqlalchemy import String, Boolean
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.dialects.postgresql import TIMESTAMP
from datetime import datetime
from . import Base, DateTimeMixin

class User(Base, DateTimeMixin):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str]
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    refresh_token: Mapped[str | None] = mapped_column(String(255))

    # Relationships
    track_hits: Mapped[list['TrackHit']] = relationship('TrackHit', back_populates='user')
    track_favorites: Mapped[list['TrackFav']] = relationship('TrackFav', back_populates='user')
    artist_favorites: Mapped[list['ArtistFav']] = relationship('ArtistFav', back_populates='user')
    playlists: Mapped[list['Playlist']] = relationship('Playlist', back_populates='user')
    playlist_hits: Mapped[list['PlaylistHit']] = relationship('PlaylistHit', back_populates='user')
    sync_meta: Mapped['SyncMeta'] = relationship('SyncMeta', back_populates='user')