# -*- encoding: utf-8 -*-
"""
Tests for app/services/scanner.py
Focus: parse_single_file 的错误兜底与 scan_progress 空值保护、文件遍历
"""

from unittest.mock import patch

import pytest

from app.core.state import system_state
from app.services.scanner import Scanner


@pytest.fixture(autouse=True)
def _reset_scan_state():
    system_state.reset_scan_state()
    yield
    system_state.reset_scan_state()


def _fake_meta(file_path) -> dict:
    return {
        'title': 'Song',
        'artists': ['A'],
        'album': 'AL',
        'albumartist': ['A'],
        'year': 2024,
        'genres': ['Rock'],
        'mb_artistids': ['aid'],
        'mb_albumartistid': ['aaid'],
        'mb_albumid': 'alid',
        'mb_trackid': 'tid',
        'acoustid_id': 'cid',
        'duration': 123.4,
        'bitrate': 320,
        'bitrate_mode': 'CBR',
    }


class TestFileIteration:
    async def test_count_and_iter_only_music_files(self, tmp_path):
        (tmp_path / 'a.mp3').write_bytes(b'x')
        (tmp_path / 'b.flac').write_bytes(b'x')
        (tmp_path / 'c.txt').write_text('x', encoding='utf-8')
        (tmp_path / 'sub').mkdir()
        (tmp_path / 'sub' / 'd.mp3').write_bytes(b'x')

        scanner = Scanner(tmp_path, is_incremental=False)

        assert await scanner.count_files() == 3
        assert sorted(p.name for p in scanner.iter_files()) == ['a.mp3', 'b.flac', 'd.mp3']


class TestParseSingleFile:
    async def test_unreadable_metadata_counts_failed(self, tmp_path):
        bad = tmp_path / 'dummy.txt'
        bad.write_text('x', encoding='utf-8')
        scanner = Scanner(tmp_path, is_incremental=False)
        system_state.init_scan_state()

        await scanner.parse_single_file(bad)

        assert system_state.scan_progress is not None
        assert system_state.scan_progress['failed'] == 1
        assert system_state.scan_progress['processed'] == 0
        assert scanner.queue.empty()

    async def test_no_scan_progress_does_not_crash(self, tmp_path):
        """scan_progress 为 None 时（未初始化扫描状态）不应抛异常"""
        bad = tmp_path / 'dummy.txt'
        bad.write_text('x', encoding='utf-8')
        scanner = Scanner(tmp_path, is_incremental=False)
        assert system_state.scan_progress is None

        await scanner.parse_single_file(bad)

        assert system_state.scan_progress is None
        assert scanner.queue.empty()

    @patch('app.services.scanner.read_metadata')
    async def test_parsed_meta_queued(self, mock_read, tmp_path):
        song = tmp_path / 'song.mp3'
        song.write_bytes(b'x')
        mock_read.side_effect = _fake_meta
        scanner = Scanner(tmp_path, is_incremental=False)

        await scanner.parse_single_file(song)

        meta = scanner.queue.get_nowait()
        assert meta is not None
        assert meta.path == str(song)
        assert meta.title == 'Song'
        assert meta.duration == 123.4
