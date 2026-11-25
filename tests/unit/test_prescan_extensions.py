# -*- encoding: utf-8 -*-
"""
Tests for prescan extension handling.
Single source of truth (settings) + one-pass, case-insensitive file collection.
"""

from pathlib import Path
from unittest.mock import patch


from prescan.scanner import InspectScanner, _default_extensions


class TestDefaultExtensions:
    def test_follows_settings(self):
        with patch('app.core.config.settings.MUSIC_FILE_EXTENSIONS',
                   ['.mp3', '.flac', '.m4a']):
            assert _default_extensions() == ['.mp3', '.flac', '.m4a']

    def test_fallback_when_settings_unavailable(self):
        with patch.dict('sys.modules', {'app.core.config': None}):
            assert '.m4a' in _default_extensions()

    def test_scanner_normalizes_extensions(self, tmp_path):
        scanner = InspectScanner(tmp_path, tmp_path / 'x.db', ['.M4A'])
        assert scanner.extensions == ['.m4a']


class TestCollectFiles:
    def test_mixed_case_and_single_walk(self, tmp_path):
        for name in ('a.m4a', 'b.M4A', 'c.M4a', 'd.mp3', 'e.txt'):
            (tmp_path / name).write_bytes(b'x')

        scanner = InspectScanner(tmp_path, tmp_path / 'x.db',
                                 ['.mp3', '.flac', '.m4a'])

        original = Path.rglob
        patterns: list[str] = []

        def counting(self, pattern):
            patterns.append(pattern)
            return original(self, pattern)

        with patch.object(Path, 'rglob', counting):
            files = scanner._collect_files()

        assert sorted(f.name for f in files) == ['a.m4a', 'b.M4A', 'c.M4a', 'd.mp3']
        assert patterns == ['*']  # exactly one full walk
