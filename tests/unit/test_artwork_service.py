# -*- encoding: utf-8 -*-
"""
Tests for app/services/artwork_service.py
ArtType must render as its value ('album'), never as 'ArtType.ALBUM':
artwork directories are ARTWORK_DIR / f'{art_type}s'.
"""

from types import SimpleNamespace

import pytest

from app.services import artwork_service as artwork_module
from app.services.artwork_service import ArtType, ArtworkService


@pytest.fixture
def service(tmp_path, monkeypatch):
    # keep raw bytes, the real resize needs a decodable image
    monkeypatch.setattr(artwork_module, 'resize_image', lambda data, *a, **k: data)
    return ArtworkService(db=None, settings=SimpleNamespace(ARTWORK_DIR=tmp_path))


class TestArtTypeStr:
    def test_fstring_renders_value(self):
        assert f'{ArtType.ALBUM}' == 'album'
        assert f'{ArtType.ALBUM}s' == 'albums'
        assert str(ArtType.ARTIST) == 'artist'
        assert '{}'.format(ArtType.TMP) == 'tmp'
        assert '%s' % ArtType.PLAYLIST == 'playlist'

    def test_members_still_compare_with_plain_strings(self):
        assert ArtType.TRACK == 'track'
        assert ArtType.PLAYLIST in {'playlist'}


class TestSaveArtworkToCache:
    async def test_album_artwork_lands_in_albums_dir(self, service, tmp_path):
        path = await service._save_artwork_to_cache(7, ArtType.ALBUM, b'jpg')
        assert path == tmp_path / 'albums' / '7.jpg'
        assert path.read_bytes() == b'jpg'

    async def test_artist_face_artwork_name(self, service, tmp_path):
        path = await service._save_artwork_to_cache(9, ArtType.ARTIST, b'jpg', 'face')
        assert path == tmp_path / 'artists' / '9_face.jpg'
        assert path.exists()

    async def test_playlist_and_tmp_dirs(self, service, tmp_path):
        assert await service._save_artwork_to_cache(1, ArtType.PLAYLIST, b'jpg') \
            == tmp_path / 'playlists' / '1.jpg'
        assert await service._save_artwork_to_cache('abc', ArtType.TMP, b'jpg') \
            == tmp_path / 'tmps' / 'abc.jpg'

    async def test_plain_string_art_type_is_accepted(self, service, tmp_path):
        path = await service._save_artwork_to_cache(3, 'track', b'jpg')
        assert path == tmp_path / 'tracks' / '3.jpg'

    async def test_invalid_art_type_returns_none(self, service):
        assert await service._save_artwork_to_cache(1, 'nope', b'jpg') is None


class TestDefaultArt:
    async def test_get_default_album_art(self, service, tmp_path):
        default = tmp_path / 'albums' / 'default.jpg'
        default.parent.mkdir(parents=True)
        default.write_bytes(b'jpg')

        assert await service.get_default_art(ArtType.ALBUM) == default.resolve()

    async def test_get_default_artist_art(self, service, tmp_path):
        default = tmp_path / 'artists' / 'default_face.jpg'
        default.parent.mkdir(parents=True)
        default.write_bytes(b'jpg')

        assert await service.get_default_art(ArtType.ARTIST) == default.resolve()

    async def test_set_default_art_writes_into_value_dir(self, service, tmp_path):
        class _Cover:
            async def read(self):
                return b'jpg'

        await service.set_default_art(ArtType.PLAYLIST, _Cover())
        assert (tmp_path / 'playlists' / 'default.jpg').read_bytes() == b'jpg'
