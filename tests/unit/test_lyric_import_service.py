# -*- encoding: utf-8 -*-
"""
Tests for app/services/lyric_import_service.py
path normalization between the external sqlite dump (unix separators, .mp3)
and the lyric table (tracks.path format, .lrc).
"""

from app.services.lyric_import_service import _decode, _posix, _to_float, to_lrc_path


class TestPathNormalization:
    def test_unix_path_gets_lrc_suffix(self):
        assert to_lrc_path('Chinese/A-G/Beyond/1-02 大厦.mp3') == 'Chinese/A-G/Beyond/1-02 大厦.lrc'

    def test_windows_path_is_normalized_to_posix(self):
        assert to_lrc_path('Chinese\\A-G\\Beyond\\aaa.flac') == 'Chinese/A-G/Beyond/aaa.lrc'

    def test_dotted_file_name_keeps_its_stem(self):
        assert to_lrc_path('a/b.c/01 song.name.mp3') == 'a/b.c/01 song.name.lrc'

    def test_posix_of_mixed_separators(self):
        assert _posix('a\\b/c\\d.lrc') == 'a/b/c/d.lrc'

    def test_lyric_and_audio_paths_meet(self):
        audio = 'Chinese\\A-G\\Beyond\\1-02 大厦.mp3'
        lyric = str('Chinese\\A-G\\Beyond\\1-02 大厦.lrc')
        assert to_lrc_path(audio) == _posix(lyric)


class TestDecode:
    def test_utf8_with_bom(self):
        assert _decode('\ufeffpath,best'.encode('utf-8')) == 'path,best'

    def test_gb18030_fallback(self):
        assert _decode('中文'.encode('gb18030')) == '中文'


class TestToFloat:
    def test_values(self):
        assert _to_float('9.5') == 9.5
        assert _to_float('') is None
        assert _to_float(None) is None
        assert _to_float('abc') is None
        assert _to_float(' 3 ') == 3.0
