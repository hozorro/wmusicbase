# -*- encoding: utf-8 -*-
'''
@File      :   __init__.py
@Time      :   2025/10/18 21:42:23
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   models init file
'''


from sqlalchemy import func
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncAttrs
from datetime import datetime

class Base(AsyncAttrs, DeclarativeBase):
    """base model of async sqlalchemy model"""
    pass

class DateTimeMixin:
    """datetime mixin model"""
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        insert_sentinel=False,
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        insert_sentinel=False,
        nullable=False,
        index=True,
    )

from .folder import Folder
from .track import Track, track_artists, track_genres
from .artist import Artist
from .album import Album
from .genre import Genre
from .user import User, UserToken
from .playback import Playlist, TrackHit, TrackFav, ArtistFav, PlaylistTrack, PlaylistHit, SyncMeta

__all__ = [
    "Folder",
    "Track",
    "track_artists",
    "track_genres",
    "Artist",
    "Album",
    "Genre",
    "User",
    "UserToken",
    "Playlist",
    "TrackHit",
    "TrackFav",
    "ArtistFav",
    "PlaylistTrack",
    "PlaylistHit",
    "SyncMeta",
]