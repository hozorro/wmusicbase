# -*- encoding: utf-8 -*-
"""
Tests for app/schemas/common.py
Validators: TrackBrief.extract_names, FolderBase.name, MediaPath.extract_path, ResponseModel
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
from pydantic import ValidationError
from app.models.artist import Artist
from app.schemas.common import (
    TrackBrief,
    FolderBase,
    MediaPath,
    ResponseModel,
)


class TestTrackBrief:
    """Tests for TrackBrief entity shape (duration/album required, artists are objects)"""

    def test_artist_objects(self):
        """List of Artist ORM objects -> validated as ArtistPrimary objects"""
        a1 = MagicMock(spec=Artist)
        a1.id = 1
        a1.name = 'Artist A'
        a2 = MagicMock(spec=Artist)
        a2.id = 2
        a2.name = 'Artist B'
        t = TrackBrief(
            id=1, title='Song', cover_art_hash=None, duration=180.0,
            album={'id': 10, 'title': 'Album X'}, artists=[a1, a2]
        )
        assert [a.id for a in t.artists] == [1, 2]
        assert [a.name for a in t.artists] == ['Artist A', 'Artist B']

    def test_dict_list(self):
        """List of dicts (id + name) -> validated as ArtistPrimary objects"""
        artists = [{'id': 1, 'name': 'Artist X'}, {'id': 2, 'name': 'Artist Y'}]
        t = TrackBrief(
            id=1, title='Song', cover_art_hash=None, duration=180.0,
            album={'id': 10, 'title': 'Album X'}, artists=artists
        )
        assert [a.name for a in t.artists] == ['Artist X', 'Artist Y']

    def test_empty_list(self):
        """Empty artists list is allowed"""
        t = TrackBrief(
            id=1, title='Song', cover_art_hash=None, duration=180.0,
            album={'id': 10, 'title': 'Album X'}, artists=[]
        )
        assert t.artists == []

    def test_album_validated_as_primary(self):
        """album is validated as AlbumPrimary (id + title)"""
        t = TrackBrief(
            id=1, title='Song', cover_art_hash=None, duration=180.0,
            album={'id': 10, 'title': 'Album X'}, artists=[]
        )
        assert t.album.id == 10
        assert t.album.title == 'Album X'

    def test_missing_required_fields(self):
        """duration and album are required"""
        with pytest.raises(ValidationError):
            TrackBrief(id=1, title='Song', cover_art_hash=None, artists=[])


class TestFolderBaseName:
    """Tests for FolderBase.name computed_field"""

    def test_music_folder(self):
        f = FolderBase(id=1, path='/music/Chinese/A-G/Artist/Album')
        assert f.name == 'Album'

    def test_root_dot(self):
        # Path('.').name returns '' on most platforms
        f = FolderBase(id=1, path='.')
        assert f.name == Path('.').name

    def test_single_name(self):
        f = FolderBase(id=1, path='root')
        assert f.name == 'root'


class TestMediaPathExtractPath:
    """Tests for MediaPath.extract_path field_validator"""

    def test_path_object(self):
        """Path object -> validator prepends [app-base] prefix"""
        m = MediaPath(name='test', path=Path('relative/dir'))
        # Result keeps the OS path separator
        assert m.path == str(Path('[app-base]') / Path('relative/dir'))

    def test_string_path(self):
        """String path -> returned as-is"""
        m = MediaPath(name='test', path='/some/string/path')
        assert m.path == '/some/string/path'

    def test_none_path(self):
        """None path -> None"""
        m = MediaPath(name='test', path=None)
        assert m.path is None


class TestResponseModel:
    """Tests for ResponseModel generic"""

    def test_with_string_data(self):
        r = ResponseModel[str](data='hello')
        assert r.code == 200
        assert r.data == 'hello'

    def test_with_list_data(self):
        r = ResponseModel[list[int]](data=[1, 2, 3])
        assert r.data == [1, 2, 3]
