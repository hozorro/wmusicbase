# -*- encoding: utf-8 -*-
'''
@File      :   models.py
@Desc      :   Lightweight SQLite models for inspection, fully independent from production models
'''


from sqlalchemy import String, Float, Integer, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Table, Column


class InspectBase(DeclarativeBase):
    pass


# ==================== Association Tables ====================

ins_track_artists = Table(
    'ins_track_artists',
    InspectBase.metadata,
    Column('track_id', Integer, ForeignKey('ins_tracks.id', ondelete='CASCADE'), primary_key=True),
    Column('artist_id', Integer, ForeignKey('ins_artists.id', ondelete='CASCADE'), primary_key=True),
)

ins_track_genres = Table(
    'ins_track_genres',
    InspectBase.metadata,
    Column('track_id', Integer, ForeignKey('ins_tracks.id', ondelete='CASCADE'), primary_key=True),
    Column('genre_id', Integer, ForeignKey('ins_genres.id', ondelete='CASCADE'), primary_key=True),
)


# ==================== Core Entity Models ====================

class InsArtist(InspectBase):
    __tablename__ = 'ins_artists'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    dir_path: Mapped[str] = mapped_column(String, nullable=False, default='')
    has_face_jpg: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_name: Mapped[str] = mapped_column(String, default='', index=True)
    pinyin_initial: Mapped[str] = mapped_column(String(1), default='_', index=True)

    # relationships
    albums: Mapped[list['InsAlbum']] = relationship('InsAlbum', back_populates='artist')
    tracks: Mapped[list['InsTrack']] = relationship('InsTrack', secondary=ins_track_artists, back_populates='artists')


class InsAlbum(InspectBase):
    __tablename__ = 'ins_albums'
    __table_args__ = (
        UniqueConstraint('title', 'artist_id', name='uq_album_title_artist'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default='')
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dir_path: Mapped[str] = mapped_column(String, nullable=False, default='')
    artist_id: Mapped[int] = mapped_column(Integer, ForeignKey('ins_artists.id', ondelete='SET NULL'), nullable=True)

    # relationships
    artist: Mapped['InsArtist'] = relationship('InsArtist', back_populates='albums')
    tracks: Mapped[list['InsTrack']] = relationship('InsTrack', back_populates='album')


class InsGenre(InspectBase):
    __tablename__ = 'ins_genres'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

    # relationships
    tracks: Mapped[list['InsTrack']] = relationship('InsTrack', secondary=ins_track_genres, back_populates='genres')


class InsTrack(InspectBase):
    __tablename__ = 'ins_tracks'
    __table_args__ = (
        Index('ix_ins_tracks_title', 'title'),
        Index('ix_ins_tracks_album_id', 'album_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String, nullable=False, default='')
    title: Mapped[str] = mapped_column(String, nullable=False, default='')
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    bitrate: Mapped[int] = mapped_column(Integer, default=0)
    bitrate_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_cover_art: Mapped[bool] = mapped_column(Boolean, default=False)
    cover_art_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    album_id: Mapped[int | None] = mapped_column(Integer, ForeignKey('ins_albums.id', ondelete='SET NULL'), nullable=True)
    dir_level: Mapped[int] = mapped_column(Integer, default=0)
    parse_error: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    # directory structure fields (extracted from file path)
    dir_area: Mapped[str | None] = mapped_column(String, nullable=True)
    dir_char_range: Mapped[str | None] = mapped_column(String, nullable=True)

    # relationships
    album: Mapped['InsAlbum | None'] = relationship('InsAlbum', back_populates='tracks')
    artists: Mapped[list['InsArtist']] = relationship('InsArtist', secondary=ins_track_artists, back_populates='tracks')
    genres: Mapped[list['InsGenre']] = relationship('InsGenre', secondary=ins_track_genres, back_populates='tracks')


# ==================== Issue Model ====================

class InsIssue(InspectBase):
    __tablename__ = 'ins_issues'
    __table_args__ = (
        Index('ix_ins_issues_check_name', 'check_name'),
        Index('ix_ins_issues_severity', 'severity'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    check_name: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)  # 'error' | 'warning' | 'info'
    entity_type: Mapped[str] = mapped_column(String, nullable=False)  # 'track' | 'artist' | 'album' | 'directory'
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
