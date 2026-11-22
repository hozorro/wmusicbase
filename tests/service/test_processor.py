# -*- encoding: utf-8 -*-
"""
tests/service/test_processor.py
Tests for MusicFileProcessor.
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from app.services.processor import MusicFileProcessor
from app.schemas.filething import ParsedMeta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_meta(**overrides) -> ParsedMeta:
    """Create a ParsedMeta with sensible defaults."""
    defaults = dict(
        path='/music/rock/artist_a/album_x/01-song.mp3',
        title='Test Song',
        artists=['Artist A'],
        album='Album X',
        albumartist=['Artist A'],
        year=2024,
        genres=['Rock'],
        mb_artistids=[None],
        mb_albumartistid=[None],
        mb_albumid=None,
        mb_trackid=None,
        acoustid_id=None,
        duration=240.0,
        bitrate=320,
        bitrate_mode='CBR',
    )
    defaults.update(overrides)
    return ParsedMeta(**defaults)


def _mock_entity(cls_name: str, **attrs):
    """Create a MagicMock that passes isinstance checks for ORM models."""
    from app.models import Genre, Artist, Album, Folder, Track
    cls_map = {'Genre': Genre, 'Artist': Artist, 'Album': Album, 'Folder': Folder, 'Track': Track}
    obj = MagicMock(spec=cls_map[cls_name])
    for k, v in attrs.items():
        setattr(obj, k, v)
    return obj


def _make_result(return_value):
    """Build a mock result object with scalar_one_or_none / scalar_one / all."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=return_value)
    result.scalar_one = MagicMock(return_value=return_value)
    result.all = MagicMock(return_value=return_value if isinstance(return_value, list) else [return_value])
    return result


@pytest.fixture
def processor(mock_db):
    root = Path('/music')
    return MusicFileProcessor(root_path=root, db=mock_db)


# ===========================================================================
# __init__
# ===========================================================================

class TestInit:
    def test_initial_caches_empty(self, processor):
        assert processor.genre_cache == {}
        assert processor.artist_cache == {}
        assert processor.album_cache == {}
        assert processor.folder_cache == {}
        assert processor.pending_tracks == []

    def test_root_path(self, processor):
        assert processor.root_path == Path('/music')


# ===========================================================================
# get_or_create_genre
# ===========================================================================

class TestGetOrCreateGenre:
    async def test_cache_hit(self, processor):
        genre = _mock_entity('Genre', id=1, name='Rock')
        processor.genre_cache['Rock'] = genre
        result = await processor.get_or_create_genre('Rock')
        assert result is genre

    async def test_db_hit(self, processor, mock_db):
        genre = _mock_entity('Genre', id=2, name='Pop')
        mock_db.execute.return_value = _make_result(genre)
        result = await processor.get_or_create_genre('Pop')
        assert result is genre
        assert 'Pop' in processor.genre_cache

    async def test_db_create_new(self, processor, mock_db):
        # first call: select -> None (not found)
        # second call: pg_insert returning new genre
        new_genre = _mock_entity('Genre', id=3, name='Jazz')
        mock_db.execute.side_effect = [
            _make_result(None),     # select -> not found
            _make_result(new_genre), # insert returning
        ]
        result = await processor.get_or_create_genre('Jazz')
        assert result is new_genre
        assert 'Jazz' in processor.genre_cache

    async def test_db_create_conflict_fallback(self, processor, mock_db):
        """pg_insert returns None (conflict), then select finds existing."""
        existing = _mock_entity('Genre', id=4, name='Blues')
        mock_db.execute.side_effect = [
            _make_result(None),    # select -> not found
            _make_result(None),    # insert -> None (conflict)
            _make_result(existing), # fallback select
        ]
        result = await processor.get_or_create_genre('Blues')
        assert result is existing


# ===========================================================================
# get_or_create_artist
# ===========================================================================

class TestGetOrCreateArtist:
    async def test_cache_hit(self, processor):
        artist = _mock_entity('Artist', id=1, name='AA')
        processor.artist_cache['AA'] = artist
        result = await processor.get_or_create_artist('AA', None)
        assert result is artist

    async def test_db_hit_mbid_update(self, processor, mock_db):
        """If existing artist has different mbid, it gets updated."""
        artist = _mock_entity('Artist', id=2, name='BB', mb_artistid=None)
        mock_db.execute.return_value = _make_result(artist)
        result = await processor.get_or_create_artist('BB', 'new-mbid')
        assert artist.mb_artistid == 'new-mbid'
        mock_db.flush.assert_awaited()
        assert result is artist

    async def test_db_hit_mbid_same_no_update(self, processor, mock_db):
        artist = _mock_entity('Artist', id=3, name='CC', mb_artistid='same-mbid')
        mock_db.execute.return_value = _make_result(artist)
        await processor.get_or_create_artist('CC', 'same-mbid')
        mock_db.flush.assert_not_awaited()

    async def test_db_create_new(self, processor, mock_db):
        new_artist = _mock_entity('Artist', id=4, name='DD')
        mock_db.execute.side_effect = [
            _make_result(None),       # select -> not found
            _make_result(new_artist),  # insert returning
        ]
        result = await processor.get_or_create_artist('DD', None)
        assert result is new_artist


# ===========================================================================
# get_or_create_album
# ===========================================================================

class TestGetOrCreateAlbum:
    async def test_cache_hit(self, processor):
        artist = _mock_entity('Artist', id=10)
        album = _mock_entity('Album', id=1, title='AL')
        processor.album_cache[('AL', 10)] = album
        result = await processor.get_or_create_album('AL', 2024, None, artist)
        assert result is album

    async def test_db_hit(self, processor, mock_db):
        artist = _mock_entity('Artist', id=20)
        album = _mock_entity('Album', id=2, title='AM')
        mock_db.execute.return_value = _make_result(album)
        result = await processor.get_or_create_album('AM', 2024, None, artist)
        assert result is album

    async def test_db_create(self, processor, mock_db):
        artist = _mock_entity('Artist', id=30)
        new_album = _mock_entity('Album', id=3, title='AN')
        mock_db.execute.side_effect = [
            _make_result(None),       # select -> not found
            _make_result(new_album),   # insert returning
        ]
        result = await processor.get_or_create_album('AN', 2024, None, artist)
        assert result is new_album


# ===========================================================================
# get_or_create_folder
# ===========================================================================

class TestGetOrCreateFolder:
    async def test_cache_hit(self, processor):
        folder = _mock_entity('Folder', id=1, path='rock/artist_a')
        # Use platform-native relative path as cache key (Windows uses backslashes)
        rel_path = str(Path('/music/rock/artist_a').relative_to(Path('/music')))
        processor.folder_cache[rel_path] = folder
        result = await processor.get_or_create_folder(Path('/music/rock/artist_a'), Path('/music'))
        assert result is folder

    async def test_root_folder_no_parent(self, processor, mock_db):
        """Root folder should have parent_id=None."""
        folder = _mock_entity('Folder', id=10, path='.')
        mock_db.execute.side_effect = [
            _make_result(None),     # select -> not found
            _make_result(folder),    # insert returning
        ]
        result = await processor.get_or_create_folder(Path('/music'), Path('/music'))
        assert result is folder

    async def test_nested_folder_creates_parent(self, processor, mock_db):
        """Nested folder should recursively create parent."""
        parent_folder = _mock_entity('Folder', id=5, path='rock')
        child_folder = _mock_entity('Folder', id=6, path='rock/artist_a')
        mock_db.execute.side_effect = [
            # child: select -> not found
            _make_result(None),
            # parent: select -> found
            _make_result(parent_folder),
            # child: insert returning
            _make_result(child_folder),
        ]
        result = await processor.get_or_create_folder(
            Path('/music/rock/artist_a'), Path('/music')
        )
        assert result is child_folder


# ===========================================================================
# update_track
# ===========================================================================

class TestUpdateTrack:
    async def test_success(self, processor, mock_db):
        track = _mock_entity('Track', id=1, title='Old')
        meta = _make_meta()
        folder = _mock_entity('Folder', id=1)
        album = _mock_entity('Album', id=1)
        artist = _mock_entity('Artist', id=1)
        genre = _mock_entity('Genre', id=1)

        result = await processor.update_track(
            track, meta, folder, album, [artist], [genre]
        )
        assert result is True
        assert track.title == 'Test Song'
        assert track.is_deleted is False
        # 2 deletes + 2 inserts (artists + genres) + flush
        assert mock_db.execute.await_count == 4
        mock_db.flush.assert_awaited()

    async def test_hash_not_touched(self, processor, mock_db):
        """update_track must not touch cover_art_hash (managed by artwork sync)."""
        track = _mock_entity('Track', id=1, title='Old', cover_art_hash='old_hash')
        meta = _make_meta()
        folder = _mock_entity('Folder', id=1)
        await processor.update_track(track, meta, folder, None, [], [])
        assert track.cover_art_hash == 'old_hash'

    async def test_no_artists_no_genres(self, processor, mock_db):
        track = _mock_entity('Track', id=2)
        meta = _make_meta()
        folder = _mock_entity('Folder', id=1)
        result = await processor.update_track(track, meta, folder, None, [], [])
        assert result is True
        # 2 deletes only (no inserts since empty lists)
        assert mock_db.execute.await_count == 2

    async def test_exception_propagates(self, processor, mock_db):
        track = _mock_entity('Track', id=3)
        meta = _make_meta()
        mock_db.execute.side_effect = Exception('db error')
        with pytest.raises(Exception, match='db error'):
            await processor.update_track(track, meta, _mock_entity('Folder', id=1), None, [], [])


# ===========================================================================
# process_single_file – album_artist inference
# ===========================================================================

class TestProcessSingleFileAlbumArtist:
    """Test the three-level album_artist inference logic."""

    async def test_albumartist_first(self, processor, mock_db):
        """albumartist[0] is used when present."""
        meta = _make_meta(albumartist=['VA'], artists=['Artist B'])
        artist_va = _mock_entity('Artist', id=1, name='VA')
        genre = _mock_entity('Genre', id=1)
        album = _mock_entity('Album', id=1)
        folder = _mock_entity('Folder', id=1)

        # mock all get_or_create calls
        processor.get_or_create_genre = AsyncMock(return_value=genre)
        processor.get_or_create_artist = AsyncMock(return_value=artist_va)
        processor.get_or_create_album = AsyncMock(return_value=album)
        processor.get_or_create_folder = AsyncMock(return_value=folder)

        await processor.process_single_file(meta, is_incremental_scan=False)
        # album_artist should be VA (from albumartist[0])
        calls = processor.get_or_create_artist.call_args_list
        # last call is the album_artist lookup
        album_artist_call = calls[-1]
        assert album_artist_call.args[0] == 'VA'

    async def test_fallback_to_artist(self, processor, mock_db):
        """When albumartist is empty, use artists[0]."""
        meta = _make_meta(albumartist=[], artists=['Artist C'])
        artist_c = _mock_entity('Artist', id=2, name='Artist C')
        genre = _mock_entity('Genre', id=1)
        album = _mock_entity('Album', id=1)
        folder = _mock_entity('Folder', id=1)

        processor.get_or_create_genre = AsyncMock(return_value=genre)
        processor.get_or_create_artist = AsyncMock(return_value=artist_c)
        processor.get_or_create_album = AsyncMock(return_value=album)
        processor.get_or_create_folder = AsyncMock(return_value=folder)

        await processor.process_single_file(meta, is_incremental_scan=False)
        calls = processor.get_or_create_artist.call_args_list
        album_artist_call = calls[-1]
        assert album_artist_call.args[0] == 'Artist C'

    async def test_fallback_unknown(self, processor, mock_db):
        """When both albumartist and artists are empty, use 'Unknown Artist'."""
        meta = _make_meta(albumartist=[], artists=[], genres=[])
        artist_unk = _mock_entity('Artist', id=99, name='Unknown Artist')
        folder = _mock_entity('Folder', id=1)

        processor.get_or_create_genre = AsyncMock(return_value=None)
        processor.get_or_create_artist = AsyncMock(return_value=artist_unk)
        processor.get_or_create_album = AsyncMock(return_value=None)
        processor.get_or_create_folder = AsyncMock(return_value=folder)

        await processor.process_single_file(meta, is_incremental_scan=False)
        calls = processor.get_or_create_artist.call_args_list
        album_artist_call = calls[-1]
        assert album_artist_call.args[0] == 'Unknown Artist'


# ===========================================================================
# process_single_file – pending_tracks
# ===========================================================================

class TestProcessSingleFilePending:
    async def test_full_scan_adds_to_pending(self, processor):
        meta = _make_meta()
        genre = _mock_entity('Genre', id=1)
        artist = _mock_entity('Artist', id=1)
        album = _mock_entity('Album', id=1)
        folder = _mock_entity('Folder', id=1)

        processor.get_or_create_genre = AsyncMock(return_value=genre)
        processor.get_or_create_artist = AsyncMock(return_value=artist)
        processor.get_or_create_album = AsyncMock(return_value=album)
        processor.get_or_create_folder = AsyncMock(return_value=folder)

        result = await processor.process_single_file(meta, is_incremental_scan=False)
        assert result is True
        assert len(processor.pending_tracks) == 1
        assert processor.pending_tracks[0]['title'] == 'Test Song'
        # cover_art_hash is deferred to artwork generation (hash <-> static file)
        assert processor.pending_tracks[0]['cover_art_hash'] is None

    async def test_incremental_scan_updates_existing(self, processor, mock_db):
        meta = _make_meta()
        genre = _mock_entity('Genre', id=1)
        artist = _mock_entity('Artist', id=1)
        album = _mock_entity('Album', id=1)
        folder = _mock_entity('Folder', id=1)
        existing_track = _mock_entity('Track', id=5, cover_art_hash='old')

        processor.get_or_create_genre = AsyncMock(return_value=genre)
        processor.get_or_create_artist = AsyncMock(return_value=artist)
        processor.get_or_create_album = AsyncMock(return_value=album)
        processor.get_or_create_folder = AsyncMock(return_value=folder)
        processor.update_track = AsyncMock(return_value=True)

        # mock db.execute for select(Track)
        mock_db.execute.return_value = _make_result(existing_track)

        result = await processor.process_single_file(meta, is_incremental_scan=True)
        assert result is True
        processor.update_track.assert_awaited_once()
        assert len(processor.pending_tracks) == 0

    async def test_incremental_scan_new_track_goes_pending(self, processor, mock_db):
        meta = _make_meta()
        genre = _mock_entity('Genre', id=1)
        artist = _mock_entity('Artist', id=1)
        album = _mock_entity('Album', id=1)
        folder = _mock_entity('Folder', id=1)

        processor.get_or_create_genre = AsyncMock(return_value=genre)
        processor.get_or_create_artist = AsyncMock(return_value=artist)
        processor.get_or_create_album = AsyncMock(return_value=album)
        processor.get_or_create_folder = AsyncMock(return_value=folder)

        # track not found
        mock_db.execute.return_value = _make_result(None)

        result = await processor.process_single_file(meta, is_incremental_scan=True)
        assert result is True
        assert len(processor.pending_tracks) == 1


# ===========================================================================
# commit_pending_tracks
# ===========================================================================

class TestCommitPendingTracks:
    async def test_empty_pending(self, processor):
        """No-op when pending_tracks is empty."""
        await processor.commit_pending_tracks()
        processor.db.execute.assert_not_awaited()

    async def test_success(self, processor, mock_db):
        processor.pending_tracks = [
            {'title': 'T1', 'path': 'rock/t1.mp3', 'folder_id': 1, 'album_id': 1,
             'duration': 200, 'bitrate': 320, 'bitrate_mode': 'CBR',
             'year': 2024, 'acoustid_id': None, 'mb_trackid': None, 'cover_art_hash': None},
        ]
        processor.temp_track_artists_map = {'rock/t1.mp3': [10]}
        processor.temp_track_genres_map = {'rock/t1.mp3': [20]}

        # mock result.all() returning (track_id, path)
        mock_result = MagicMock()
        mock_result.all.return_value = [(100, 'rock/t1.mp3')]
        mock_db.execute.return_value = mock_result

        await processor.commit_pending_tracks()
        # insert tracks + insert artists + insert genres + commit
        assert mock_db.execute.await_count == 3
        mock_db.commit.assert_awaited_once()
        # caches cleared
        assert processor.pending_tracks == []
        assert processor.temp_track_artists_map == {}
        assert processor.temp_track_genres_map == {}

    async def test_sqlalchemy_error_rollback(self, processor, mock_db):
        from sqlalchemy.exc import SQLAlchemyError
        processor.pending_tracks = [
            {'title': 'T2', 'path': 'rock/t2.mp3'},
        ]
        mock_db.execute.side_effect = SQLAlchemyError('fail')

        await processor.commit_pending_tracks()
        mock_db.rollback.assert_awaited_once()
        assert processor.pending_tracks == []

    async def test_generic_error_rollback(self, processor, mock_db):
        processor.pending_tracks = [
            {'title': 'T3', 'path': 'rock/t3.mp3'},
        ]
        mock_db.execute.side_effect = RuntimeError('boom')

        await processor.commit_pending_tracks()
        mock_db.rollback.assert_awaited_once()
        assert processor.pending_tracks == []

    async def test_no_artist_genre_relations(self, processor, mock_db):
        """When no artists/genres, only track insert + commit."""
        processor.pending_tracks = [
            {'title': 'T4', 'path': 'rock/t4.mp3'},
        ]
        processor.temp_track_artists_map = {'rock/t4.mp3': []}
        processor.temp_track_genres_map = {'rock/t4.mp3': []}

        mock_result = MagicMock()
        mock_result.all.return_value = [(200, 'rock/t4.mp3')]
        mock_db.execute.return_value = mock_result

        await processor.commit_pending_tracks()
        # only track insert (no association inserts since empty)
        assert mock_db.execute.await_count == 1
        mock_db.commit.assert_awaited_once()
