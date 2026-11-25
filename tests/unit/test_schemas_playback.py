# -*- encoding: utf-8 -*-
"""
Tests for app/schemas/playback.py
Validators: PlaylistImport, PlaylistImportRoot,
            HitImport, FavImport, OperationImport, OperationImportRoot,
            JsonImportResponse
"""

import pytest
from datetime import datetime
from pydantic import ValidationError
from app.schemas.playback import (
    PlaylistImport,
    PlaylistImportRoot,
    HitImport,
    FavImport,
    HitImportRoot,
    FavImportRoot,
    JsonImportResponse,
)


class TestPlaylistImport:
    """Tests for PlaylistImport and its validators"""

    def test_valid_tracks(self):
        p = PlaylistImport(
            title='My Playlist',
            tracks=['Chinese/A-G/Artist/Album/song.mp3', 'Foreign/A-G/Artist/Album/song.flac']
        )
        assert p.title == 'My Playlist'
        assert p.tracks == ['Chinese/A-G/Artist/Album/song.mp3', 'Foreign/A-G/Artist/Album/song.flac']

    def test_valid_m4a_track(self):
        p = PlaylistImport(
            title='My Playlist',
            tracks=['Chinese/A-G/Artist/Album/song.m4a']
        )
        assert p.tracks == ['Chinese/A-G/Artist/Album/song.m4a']

    def test_none_tracks(self):
        """tracks=None should pass validation (validator must not iterate None)"""
        p = PlaylistImport(title='My Playlist', tracks=None)
        assert p.tracks is None

    def test_omitted_tracks(self):
        """tracks omitted defaults to None"""
        p = PlaylistImport(title='My Playlist')
        assert p.tracks is None

    def test_invalid_track_path(self):
        with pytest.raises(ValidationError, match='Track path must be relative to music library root'):
            PlaylistImport(title='My Playlist', tracks=['Other/Artist/Album/song.mp3'])

    def test_mixed_valid_invalid_track_path(self):
        with pytest.raises(ValidationError, match='Track path must be relative to music library root'):
            PlaylistImport(title='My Playlist', tracks=['Chinese/song.mp3', 'Other/song.mp3'])

    def test_title_required(self):
        with pytest.raises(ValidationError):
            PlaylistImport.model_validate({'tracks': ['Chinese/song.mp3']})

    def test_title_too_long(self):
        with pytest.raises(ValidationError):
            PlaylistImport(title='x' * 101, tracks=['Chinese/song.mp3'])

    def test_comment_optional(self):
        p = PlaylistImport(title='My Playlist', comment=None, tracks=['Chinese/song.mp3'])
        assert p.comment is None

    def test_id_optional(self):
        p = PlaylistImport(title='My Playlist', tracks=['Chinese/song.mp3'])
        assert p.id is None


class TestPlaylistImportRoot:
    """Tests for PlaylistImportRoot.validate_root"""

    def test_empty_list(self):
        with pytest.raises(ValidationError, match='Playlists array is empty'):
            PlaylistImportRoot(root=[])

    def test_exceeds_limit(self):
        items = [
            PlaylistImport(title=f'Playlist {i}', tracks=['Chinese/song.mp3'])
            for i in range(51)
        ]
        with pytest.raises(ValidationError, match='50 playlists'):
            PlaylistImportRoot(root=items)

    def test_boundary_50(self):
        items = [
            PlaylistImport(title=f'Playlist {i}', tracks=['Chinese/song.mp3'])
            for i in range(50)
        ]
        root = PlaylistImportRoot(root=items)
        assert len(root.root) == 50

    def test_from_list_of_dict(self):
        """RootModel can be built from a raw list of dicts (as import does)"""
        root = PlaylistImportRoot.model_validate([
            {'title': 'P1', 'tracks': ['Chinese/a.mp3']},
            {'title': 'P2', 'tracks': None},
        ])
        assert len(root.root) == 2
        assert root.root[1].tracks is None


class TestHitImport:
    """Tests for HitImport.validate_played_at"""

    def test_valid_played_at(self):
        h = HitImport(track='Chinese/song.mp3', played_at='2023-06-15T10:30:00')
        assert isinstance(h.played_at, datetime)

    def test_valid_played_at_with_timezone(self):
        h = HitImport(track='Chinese/song.mp3', played_at='2023-06-15T10:30:00.000+08:00')
        assert isinstance(h.played_at, datetime)

    def test_invalid_played_at(self):
        with pytest.raises(ValidationError):
            HitImport(track='Chinese/song.mp3', played_at='not-a-date')


class TestFavImport:
    """Tests for FavImport.validate_favorited_at"""

    def test_valid_favorited_at(self):
        f = FavImport(track='Chinese/song.mp3', favorited_at='2023-06-15T10:30:00')
        assert isinstance(f.favorited_at, datetime)

    def test_invalid_favorited_at(self):
        with pytest.raises(ValidationError):
            FavImport(track='Chinese/song.mp3', favorited_at='invalid')


class TestOperationImport:
    """Tests for OperationImport.validate_path (inherited by HitImport/FavImport)"""

    def test_chinese_track_path(self):
        h = HitImport(track='Chinese/song.mp3', played_at='2023-01-01T00:00:00')
        assert h.track == 'Chinese/song.mp3'

    def test_foreign_track_path(self):
        h = HitImport(track='Foreign/song.mp3', played_at='2023-01-01T00:00:00')
        assert h.track == 'Foreign/song.mp3'

    def test_invalid_track_path(self):
        with pytest.raises(ValidationError, match='Path is relative to music library root'):
            HitImport(track='unknown/song.mp3', played_at='2023-01-01T00:00:00')


class TestOperationImportRoot:
    """Tests for OperationImportRoot.validate_root"""

    def test_empty_hit_list(self):
        with pytest.raises(ValidationError, match='Operations array is empty'):
            HitImportRoot(root=[])

    def test_empty_fav_list(self):
        with pytest.raises(ValidationError, match='Operations array is empty'):
            FavImportRoot(root=[])

    def test_exceeds_limit_hit(self):
        items = [
            HitImport(track='Chinese/song.mp3', played_at='2023-01-01T00:00:00')
            for _ in range(10001)
        ]
        with pytest.raises(ValidationError, match='10000 operations'):
            HitImportRoot(root=items)

    def test_boundary_10000(self):
        items = [
            HitImport(track='Chinese/song.mp3', played_at='2023-01-01T00:00:00')
            for _ in range(10000)
        ]
        root = HitImportRoot(root=items)
        assert len(root.root) == 10000


class TestJsonImportResponse:
    """Tests for JsonImportResponse fields (incl. new skipped count)"""

    def test_defaults(self):
        r = JsonImportResponse()
        assert r.total == 0
        assert r.success == 0
        assert r.skipped == 0
        assert r.failed == 0
        assert r.errors == []

    def test_validate_from_stats_dict(self):
        """model_validate maps the stats dict returned by import services"""
        stats = {
            'total': 3,
            'success': 1,
            'skipped': 1,
            'failed': 1,
            'errors': ['Index 0: skipped', 'Index 2: Failed to import - x'],
        }
        r = JsonImportResponse.model_validate(stats)
        assert r.total == 3
        assert r.success == 1
        assert r.skipped == 1
        assert r.failed == 1
        assert r.errors == ['Index 0: skipped', 'Index 2: Failed to import - x']
