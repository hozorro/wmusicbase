# -*- encoding: utf-8 -*-
'''
@File      :   playback.py
@Time      :   2025/10/18 22:26:05
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   play back models, hit, favorite, playlist
'''


from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from . import User, Track, Artist

from sqlalchemy import String, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from . import Base, DateTimeMixin

class TrackHit(Base):
    __tablename__ = 'track_hits'

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey('tracks.id', ondelete='CASCADE'))
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    played_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), index=True)

    track: Mapped['Track'] = relationship('Track', back_populates='play_hits')
    user: Mapped['User'] = relationship('User', back_populates='track_hits')

    __table_args__ = (Index('ix_track_hits_track_id', 'track_id'),)

class TrackFav(Base):
    __tablename__ = 'track_favorites'

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey('tracks.id', ondelete='CASCADE'), primary_key=True)
    favorited_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    user: Mapped['User'] = relationship('User', back_populates='track_favorites')
    track: Mapped['Track'] = relationship('Track', back_populates='favorites')

    __table_args__ = (UniqueConstraint('user_id', 'track_id'),)

class ArtistFav(Base):
    __tablename__ = 'artist_favorites'

    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    artist_id: Mapped[int] = mapped_column(ForeignKey('artists.id', ondelete='CASCADE'), primary_key=True)
    favorited_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    user: Mapped['User'] = relationship('User', back_populates='artist_favorites')
    artist: Mapped['Artist'] = relationship('Artist', back_populates='favorite_by')

    __table_args__ = (UniqueConstraint('user_id', 'artist_id'),)

class Playlist(Base, DateTimeMixin):
    __tablename__ = 'playlists'

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    comment: Mapped[str | None]
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)

    user: Mapped['User'] = relationship('User', back_populates='playlists')
    tracks: Mapped[list['Track']] = relationship('Track', secondary='playlist_tracks', back_populates='playlists')

class PlaylistTrack(Base):
    __tablename__ = 'playlist_tracks'

    playlist_id: Mapped[int] = mapped_column(ForeignKey('playlists.id', ondelete='CASCADE'), primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey('tracks.id', ondelete='CASCADE'), primary_key=True)
    position: Mapped[int] = mapped_column() # 在播放列表中的顺序

    __table_args__ = (
        Index('ix_playlist_tracks_playlist_id', 'playlist_id'),
        Index('ix_playlist_tracks_position', 'playlist_id', 'position'),
    )