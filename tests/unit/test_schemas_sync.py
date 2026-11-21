# -*- encoding: utf-8 -*-
"""
Tests for app/schemas/sync.py
Sync schemas for frontend indexeddb incremental sync:
SyncArtistRef, SyncAlbumRef, SyncTrack, SyncArtist, SyncAlbum,
SyncGenre, SyncFolder(from_model), SyncPlaylistTrackRef, SyncPlaylist,
SyncPullResponse, SyncSummary
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from pydantic import ValidationError

from app.models.album import Album
from app.models.artist import Artist
from app.models.folder import Folder
from app.models.genre import Genre
from app.schemas.sync import (
    SyncAlbum,
    SyncAlbumRef,
    SyncArtist,
    SyncArtistRef,
    SyncFolder,
    SyncGenre,
    SyncPlaylist,
    SyncPlaylistTrackRef,
    SyncPullResponse,
    SyncSummary,
    SyncTrack,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_model(cls, **attrs):
    """Create a MagicMock that passes isinstance checks for ORM models."""
    obj = MagicMock(spec=cls)
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


# ===========================================================================
# SyncArtistRef / SyncAlbumRef
# ===========================================================================

class TestSyncRefs:
    """Tests for the embedded reference schemas"""

    def test_artist_ref_from_dict(self):
        ref = SyncArtistRef.model_validate({'id': 1, 'name': 'Artist A'})
        assert ref.id == 1
        assert ref.name == 'Artist A'

    def test_artist_ref_from_orm_object(self):
        """from_attributes: validate directly from an ORM-like artist"""
        artist = _mock_model(Artist, id=2, name='Artist B')
        ref = SyncArtistRef.model_validate(artist)
        assert ref.id == 2
        assert ref.name == 'Artist B'

    def test_album_ref_from_dict(self):
        ref = SyncAlbumRef.model_validate({'id': 10, 'title': 'Album X'})
        assert ref.id == 10
        assert ref.title == 'Album X'

    def test_album_ref_from_orm_object(self):
        """from_attributes: validate directly from an ORM-like album"""
        album = _mock_model(Album, id=11, title='Album Y')
        ref = SyncAlbumRef.model_validate(album)
        assert ref.id == 11
        assert ref.title == 'Album Y'

    def test_artist_ref_missing_required(self):
        with pytest.raises(ValidationError):
            SyncArtistRef.model_validate({'id': 1})


# ===========================================================================
# SyncTrack
# ===========================================================================

class TestSyncTrack:
    """Tests for SyncTrack entity shape"""

    def test_minimal_with_defaults(self):
        """Only required fields -> defaults applied"""
        t = SyncTrack(id=1, title='Song', duration=180.0, folder_id=5)
        assert t.artists == []
        assert t.album is None
        assert t.cover_art_hash is None
        assert t.year is None
        assert t.genre_ids == []
        assert t.created_at is None
        assert t.favorited_at is None
        assert t.hits is None

    def test_full_dict_input(self):
        """Full payload with nested artists/album dicts"""
        data = {
            'id': 1,
            'title': 'Song 1',
            'artists': [
                {'id': 1, 'name': 'Artist A'},
                {'id': 2, 'name': 'Artist B'},
            ],
            'album': {'id': 10, 'title': 'Album X'},
            'duration': 240.5,
            'cover_art_hash': 'abc123',
            'year': 2024,
            'genre_ids': [1, 2],
            'folder_id': 5,
            'created_at': '2026-01-01T00:00:00',
            'favorited_at': '2026-02-01T00:00:00',
            'hits': ['2026-03-01T00:00:00', '2026-03-02T00:00:00'],
        }
        t = SyncTrack.model_validate(data)
        assert len(t.artists) == 2
        assert t.artists[0].name == 'Artist A'
        assert t.album.title == 'Album X'
        assert t.genre_ids == [1, 2]
        assert len(t.hits) == 2
        assert isinstance(t.favorited_at, datetime)

    def test_album_from_orm_object(self):
        """sync_service passes the ORM album object directly (from_attributes)"""
        album = _mock_model(Album, id=10, title='Album X')
        t = SyncTrack(id=1, title='Song', duration=1.0, folder_id=1, album=album)
        assert isinstance(t.album, SyncAlbumRef)
        assert t.album.id == 10
        assert t.album.title == 'Album X'

    def test_artists_from_orm_objects(self):
        """sync_service validates ORM artists via SyncArtistRef.model_validate"""
        artists = [
            SyncArtistRef.model_validate(_mock_model(Artist, id=1, name='A')),
            SyncArtistRef.model_validate(_mock_model(Artist, id=2, name='B')),
        ]
        t = SyncTrack(id=1, title='Song', duration=1.0, folder_id=1, artists=artists)
        assert [a.id for a in t.artists] == [1, 2]

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            SyncTrack(id=1, title='Song', folder_id=1)  # duration missing


# ===========================================================================
# SyncArtist
# ===========================================================================

class TestSyncArtist:
    """Tests for SyncArtist entity shape"""

    def test_defaults(self):
        a = SyncArtist(id=1, name='Artist A', pinyin_initial='A')
        assert a.face_art_hash is None
        assert a.portrait_art_hash is None
        assert a.track_count == 0
        assert a.favorited_at is None
        assert a.hit_count is None

    def test_full_values(self):
        a = SyncArtist(
            id=1, name='Artist A', pinyin_initial='A',
            face_art_hash='face_hash', portrait_art_hash='portrait_hash',
            track_count=10, favorited_at=datetime(2026, 1, 1), hit_count=5,
        )
        assert a.face_art_hash == 'face_hash'
        assert a.portrait_art_hash == 'portrait_hash'
        assert a.track_count == 10
        assert a.hit_count == 5

    def test_missing_pinyin_initial(self):
        with pytest.raises(ValidationError):
            SyncArtist(id=1, name='Artist A')


# ===========================================================================
# SyncAlbum
# ===========================================================================

class TestSyncAlbum:
    """Tests for SyncAlbum entity shape"""

    def test_defaults(self):
        a = SyncAlbum(id=1, title='Album X')
        assert a.album_artist is None
        assert a.artists == []
        assert a.cover_art_hash is None
        assert a.track_count == 0

    def test_album_artist_from_orm_object(self):
        """sync_service passes the ORM album_artist object directly"""
        artist = _mock_model(Artist, id=3, name='Artist C')
        a = SyncAlbum(id=1, title='Album X', album_artist=artist)
        assert isinstance(a.album_artist, SyncArtistRef)
        assert a.album_artist.name == 'Artist C'

    def test_artists_dedup_done_by_service(self):
        """artists list is kept as provided (dedup is service responsibility)"""
        a = SyncAlbum(
            id=1, title='Album X',
            artists=[
                SyncArtistRef(id=1, name='A'),
                SyncArtistRef(id=2, name='B'),
            ],
            track_count=3,
        )
        assert len(a.artists) == 2
        assert a.track_count == 3


# ===========================================================================
# SyncGenre
# ===========================================================================

class TestSyncGenre:
    """Tests for SyncGenre entity shape"""

    def test_from_dict(self):
        g = SyncGenre.model_validate({'id': 1, 'name': 'Rock', 'color': '#ff0000'})
        assert g.name == 'Rock'
        assert g.color == '#ff0000'

    def test_color_default_none(self):
        g = SyncGenre.model_validate({'id': 1, 'name': 'Rock'})
        assert g.color is None

    def test_from_orm_object(self):
        """sync_service validates ORM genres via model_validate (from_attributes)"""
        genre = _mock_model(Genre, id=2, name='Pop', color='#00ff00')
        g = SyncGenre.model_validate(genre)
        assert g.id == 2
        assert g.name == 'Pop'


# ===========================================================================
# SyncFolder
# ===========================================================================

class TestSyncFolder:
    """Tests for SyncFolder.from_model (name derived from path)"""

    def test_from_model_nested_path(self):
        folder = _mock_model(Folder, id=1, path='rock/artist_a/album_x', parent_id=2)
        f = SyncFolder.from_model(folder)
        assert f.id == 1
        assert f.name == 'album_x'
        assert f.parent_id == 2

    def test_from_model_root_path(self):
        """Root folder path '.' -> empty name (Path('.').name == '')"""
        folder = _mock_model(Folder, id=2, path='.', parent_id=None)
        f = SyncFolder.from_model(folder)
        assert f.name == ''
        assert f.parent_id is None

    def test_from_model_single_segment(self):
        folder = _mock_model(Folder, id=3, path='rock', parent_id=2)
        f = SyncFolder.from_model(folder)
        assert f.name == 'rock'


# ===========================================================================
# SyncPlaylist
# ===========================================================================

class TestSyncPlaylist:
    """Tests for SyncPlaylist entity shape"""

    def test_defaults(self):
        p = SyncPlaylist(id=1, title='Playlist 1', created_at=datetime(2026, 1, 1))
        assert p.comment is None
        assert p.cover_art_hash is None
        assert p.tracks == []
        assert p.hit_count is None

    def test_with_track_refs(self):
        p = SyncPlaylist(
            id=1, title='Playlist 1',
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            tracks=[
                SyncPlaylistTrackRef(id=10, position=1),
                SyncPlaylistTrackRef(id=20, position=2),
            ],
            hit_count=8,
        )
        assert [t.id for t in p.tracks] == [10, 20]
        assert [t.position for t in p.tracks] == [1, 2]
        assert p.hit_count == 8

    def test_tracks_from_dicts(self):
        p = SyncPlaylist(
            id=1, title='Playlist 1',
            created_at=datetime(2026, 1, 1),
            tracks=[{'id': 10, 'position': 1}],
        )
        assert isinstance(p.tracks[0], SyncPlaylistTrackRef)

    def test_missing_created_at(self):
        with pytest.raises(ValidationError):
            SyncPlaylist(id=1, title='Playlist 1')


# ===========================================================================
# SyncPullResponse
# ===========================================================================

class TestSyncPullResponse:
    """Tests for SyncPullResponse"""

    def test_empty_items(self):
        r = SyncPullResponse(items=[])
        assert r.items == []
        assert r.next_after_id is None

    def test_mixed_items(self):
        """items is a union of all six sync entity types"""
        r = SyncPullResponse(
            items=[
                SyncTrack(id=1, title='Song', duration=1.0, folder_id=1),
                SyncArtist(id=1, name='Artist A', pinyin_initial='A'),
                SyncGenre(id=1, name='Rock'),
            ],
            next_after_id=1,
        )
        assert len(r.items) == 3
        assert r.next_after_id == 1


# ===========================================================================
# SyncSummary
# ===========================================================================

class TestSyncSummary:
    """Tests for SyncSummary (serverTime alias, deleted optional)"""

    def test_full_sync_shape(self):
        """Full sync: counts only, deleted is None"""
        s = SyncSummary(
            counts={'tracks': 100, 'albums': 10},
            serverTime=datetime.now(tz=timezone.utc),
        )
        assert s.counts['tracks'] == 100
        assert s.deleted is None

    def test_incremental_sync_shape(self):
        """Incremental sync: deleted ids carried per store"""
        s = SyncSummary(
            counts={'tracks': 5},
            deleted={'tracks': [1, 2], 'playlists': [3]},
            serverTime=datetime.now(tz=timezone.utc),
        )
        assert s.deleted['tracks'] == [1, 2]

    def test_server_time_serialized_key(self):
        """JSON payload must keep the camelCase 'serverTime' key"""
        s = SyncSummary(
            counts={},
            serverTime=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        dumped = s.model_dump(by_alias=True)
        assert 'serverTime' in dumped

    def test_missing_server_time(self):
        with pytest.raises(ValidationError):
            SyncSummary(counts={})
