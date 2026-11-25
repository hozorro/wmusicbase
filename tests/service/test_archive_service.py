# -*- encoding: utf-8 -*-
"""Archiving must produce a lowercase extension so Track.path stays stable.

Initial library scan / watcher use the on-disk path verbatim (see
Scanner.parse_single_file and MusicLibraryHandler); lowercasing those suffixes
is an out-of-project operation performed before the first scan.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.file_service import ArchiveService


class _Settings:
    def __init__(self, root: Path):
        self.STAGING_DIR = root / 'staging'
        self.MUSIC_LIBRARY_PATH = root / 'library'
        self.MUSIC_FILE_EXTENSIONS = ['.mp3', '.flac', '.m4a']
        self.DEBUG = False
        self.LOG_DIR = root / 'logs'
        self.PLAYLISTS_TMP_DIR = root / 'playlists'


META = {
    'title': 'Take It All',
    'albumartist': ['Adele'],
    'artists': ['Adele'],
    'album': '21',
}


def _service(settings) -> ArchiveService:
    request = MagicMock()
    request.state.user_id = 1
    return ArchiveService(MagicMock(), settings, request)


def _stage(root: Path, suffix: str) -> tuple[_Settings, str, str]:
    settings = _Settings(root)
    songs = settings.STAGING_DIR / 's1' / 'songs'
    songs.mkdir(parents=True)
    settings.MUSIC_LIBRARY_PATH.mkdir(parents=True)
    item = 'a' * 32 + '_' + f'raw{suffix}'
    (songs / item).write_bytes(b'x')
    return settings, 's1', item


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix,expected', [
    ('.MP3', '.mp3'), ('.FLAC', '.flac'), ('.M4A', '.m4a'), ('.M4a', '.m4a'),
])
async def test_title_branch_archives_with_lowercase_suffix(tmp_path, suffix, expected):
    settings, session_id, item = _stage(tmp_path, suffix)
    service = _service(settings)

    with patch('app.services.file_service.read_metadata', return_value=META), \
         patch('app.services.file_service.shutil.move') as move:
        result = await service.archive_session(session_id, [item], 'EN', False, None)

    assert result['archived'] == [item]
    target = Path(move.call_args.args[1])
    assert target.suffix == expected
    assert target.name == 'Take It All' + expected


@pytest.mark.asyncio
@pytest.mark.parametrize('original,expected', [
    ('07. Take It All.FLAC', '07. Take It All.flac'),
    ('07. Take It All.M4A', '07. Take It All.m4a'),
    ('07. Take It All.MP3', '07. Take It All.mp3'),
])
async def test_original_name_branch_archives_with_lowercase_suffix(tmp_path, original, expected):
    settings = _Settings(tmp_path)
    songs = settings.STAGING_DIR / 's1' / 'songs'
    songs.mkdir(parents=True)
    settings.MUSIC_LIBRARY_PATH.mkdir(parents=True)
    item = 'a' * 32 + '_' + original
    (songs / item).write_bytes(b'x')
    service = _service(settings)

    with patch('app.services.file_service.read_metadata', return_value=META), \
         patch('app.services.file_service.shutil.move') as move:
        result = await service.archive_session('s1', [item], 'EN', True, None)

    assert result['archived'] == [item]
    assert Path(move.call_args.args[1]).name == expected


@pytest.mark.asyncio
async def test_non_audio_suffix_is_still_skipped(tmp_path):
    settings, session_id, item = _stage(tmp_path, '.TXT')
    service = _service(settings)

    with patch('app.services.file_service.shutil.move') as move:
        result = await service.archive_session(session_id, [item], 'EN', False, None)

    assert result['skipped'] == [item]
    move.assert_not_called()
