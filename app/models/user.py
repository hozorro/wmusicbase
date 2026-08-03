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
    from . import TrackHit, TrackFav, ArtistFav, ArtistHit, Playlist, PlaylistHit, SyncMeta

from sqlalchemy import String, Boolean, ForeignKey, TIMESTAMP, func, Index
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

    # Relationships
    track_hits: Mapped[list['TrackHit']] = relationship('TrackHit', back_populates='user')
    track_favorites: Mapped[list['TrackFav']] = relationship('TrackFav', back_populates='user')
    artist_favorites: Mapped[list['ArtistFav']] = relationship('ArtistFav', back_populates='user')
    artist_hits: Mapped[list['ArtistHit']] = relationship('ArtistHit', back_populates='user')
    playlists: Mapped[list['Playlist']] = relationship('Playlist', back_populates='user')
    playlist_hits: Mapped[list['PlaylistHit']] = relationship('PlaylistHit', back_populates='user')
    sync_meta: Mapped['SyncMeta'] = relationship('SyncMeta', back_populates='user')

    tokens: Mapped[list['UserToken']] = relationship('UserToken', back_populates='user', cascade='all, delete-orphan')

class UserToken(Base):
    __tablename__ = 'user_tokens'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    client_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    access_token_jti: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_used_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), default=func.now(), nullable=False)

    user = relationship('User', back_populates='tokens')

    __table_args__ = (
        Index('ix_user_tokens_unique', 'user_id', 'client_type', 'device_id', unique=True),
        Index('ix_user_tokens_user_client', 'user_id', 'client_type')
    )