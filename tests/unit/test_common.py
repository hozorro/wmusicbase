# -*- encoding: utf-8 -*-
"""
Tests for app/utils/common.py
Functions: parse_year, parse_multiple_value
"""

from pathlib import Path

from app.utils.common import normalize_music_filename, parse_year, parse_multiple_value


class TestParseYear:
    """Tests for parse_year(date_str: str) -> int | None"""

    def test_standard_year(self):
        assert parse_year('2023') == 2023

    def test_iso_date(self):
        assert parse_year('2023-05-01') == 2023

    def test_slash_date(self):
        assert parse_year('1999/12/31') == 1999

    def test_empty_string(self):
        assert parse_year('') is None

    def test_none(self):
        assert parse_year(None) is None

    def test_non_digit(self):
        assert parse_year('abcd') is None

    def test_short_number(self):
        assert parse_year('90s') is None

    def test_long_digit_string(self):
        # Only takes first 4 chars: "2023" -> 2023
        assert parse_year('20231201') == 2023

    def test_leading_spaces(self):
        # First 4 chars: "  20" -> digits "20" -> only 2 digits -> None
        assert parse_year('  2023') is None

    def test_all_zeros(self):
        # "0000" -> int("0000") = 0
        assert parse_year('0000') == 0


class TestParseMultipleValue:
    """Tests for parse_multiple_value(value: str | None) -> list[str] | None"""

    def test_none_returns_none(self):
        assert parse_multiple_value(None) is None

    def test_empty_returns_none(self):
        assert parse_multiple_value('') is None

    def test_single_value(self):
        assert parse_multiple_value('Rock') == ['Rock']

    def test_semicolon(self):
        assert parse_multiple_value('Rock;Pop') == ['Rock', 'Pop']

    def test_comma(self):
        assert parse_multiple_value('A,B') == ['A', 'B']

    def test_chinese_comma(self):
        assert parse_multiple_value('A，B') == ['A', 'B']

    def test_ampersand(self):
        assert parse_multiple_value('A&B') == ['A', 'B']

    def test_pipe(self):
        assert parse_multiple_value('A|B') == ['A', 'B']

    def test_slash(self):
        assert parse_multiple_value('A/B') == ['A', 'B']

    def test_backslash(self):
        assert parse_multiple_value('A\\B') == ['A', 'B']

    def test_mixed_separators(self):
        result = parse_multiple_value('A;B,C')
        assert result == ['A', 'B', 'C']

    def test_strip_whitespace(self):
        result = parse_multiple_value('  X  ;  Y  ')
        assert result == ['X', 'Y']


class TestNormalizeMusicFilename:
    """Only the extension is lowercased; the stem must stay byte-for-byte."""

    def test_lowercases_mp3_flac_m4a(self):
        assert normalize_music_filename('Song.MP3') == 'Song.mp3'
        assert normalize_music_filename('Song.FLAC') == 'Song.flac'
        assert normalize_music_filename('Song.M4A') == 'Song.m4a'

    def test_mixed_case_and_dotted_stem(self):
        assert normalize_music_filename('07. Take It All.M4a') == '07. Take It All.m4a'
        assert normalize_music_filename('a.b.Mp3') == 'a.b.mp3'

    def test_already_lowercase_is_unchanged(self):
        assert normalize_music_filename('Song.m4a') == 'Song.m4a'
        assert normalize_music_filename('Song.mp3') == 'Song.mp3'

    def test_no_extension_is_unchanged(self):
        assert normalize_music_filename('Song') == 'Song'
        assert normalize_music_filename('.hidden') == '.hidden'

    def test_parent_path_is_preserved(self):
        result = Path(normalize_music_filename('sub/Song.MP3'))
        assert result.name == 'Song.mp3'
        assert result.parent.name == 'sub'
