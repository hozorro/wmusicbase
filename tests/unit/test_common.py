# -*- encoding: utf-8 -*-
"""
Tests for app/utils/common.py
Functions: parse_year, parse_multiple_value
"""

from app.utils.common import parse_year, parse_multiple_value


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
    """Tests for parse_multiple_value(value: str) -> list[str] | None"""

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
