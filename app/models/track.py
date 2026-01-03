# -*- encoding: utf-8 -*-
'''
@File      :   track.py
@Time      :   2025/10/18 21:51:52
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   track model
'''


from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from . import Folder, Album, Artist, Genre, TrackHit, TrackFav, Playlist

from sqlalchemy import Table, Column, Integer, String, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime
from . import Base, DateTimeMixin

track_artists = Table(
    'track_artists',
    Base.metadata,
    Column('track_id', Integer, ForeignKey('tracks.id', ondelete='CASCADE'), primary_key=True),
    Column('artist_id', Integer, ForeignKey('artists.id', ondelete='CASCADE'), primary_key=True),

    Index('ix_track_artist_track_id', 'track_id'),
    Index('ix_track_artist_artist_id', 'artist_id'),
)

track_genres = Table(
    'track_genres',
    Base.metadata,
    Column('track_id', Integer, ForeignKey('tracks.id', ondelete='CASCADE'), primary_key=True),
    Column('genre_id', Integer, ForeignKey('genres.id', ondelete='CASCADE'), primary_key=True),

    Index('ix_track_genre_track_id', 'track_id'),
    Index('ix_track_genre_genre_id', 'genre_id'),
)

class Track(Base, DateTimeMixin):
    __tablename__ = 'tracks'

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    duration: Mapped[float]
    bitrate: Mapped[int | None]
    bitrate_mode: Mapped[str | None]
    year: Mapped[int | None]
    acoustid_id: Mapped[str | None]
    mb_trackid: Mapped[str | None]
    cover_art_hash: Mapped[str | None] = mapped_column(String(40), index=True)
    path: Mapped[str] = mapped_column(unique=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # Foreign Keys
    folder_id: Mapped[int] = mapped_column(ForeignKey('folders.id', ondelete='CASCADE'))
    album_id: Mapped[int | None] = mapped_column(ForeignKey('albums.id', ondelete='SET NULL'))

    # Relationships
    folder: Mapped['Folder'] = relationship('Folder', back_populates='tracks')
    album: Mapped[Optional['Album']] = relationship('Album', back_populates='tracks')
    artists: Mapped[list['Artist']] = relationship(secondary='track_artists', back_populates='tracks')
    genres: Mapped[list['Genre']] = relationship(secondary='track_genres', back_populates='tracks')

    # Playback
    favorites: Mapped[list['TrackFav']] = relationship('TrackFav', back_populates='track', cascade='all, delete-orphan')
    play_hits: Mapped[list['TrackHit']] = relationship('TrackHit', back_populates='track', cascade='all, delete-orphan')
    playlists: Mapped[list['Playlist']] = relationship('Playlist', secondary='playlist_tracks', back_populates='tracks')

    __table_args__ = (
        Index('ix_tracks_path', 'path'),
        Index('ix_tracks_album_id', 'album_id'),
        Index('ix_tracks_is_deleted', 'is_deleted'),
        Index('ix_tracks_has_cover', 'cover_art_hash'),
        UniqueConstraint('path', name='uq_track_path')
    )