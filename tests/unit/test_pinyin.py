# -*- encoding: utf-8 -*-
"""
Tests for app/utils/pinyin.py
Functions: normalize_initial, get_artist_sort_fields
"""

from app.utils.pinyin import normalize_initial, get_artist_sort_fields


class TestNormalizeInitial:
    """Tests for normalize_initial(char: str) -> str"""

    def test_uppercase_letter(self):
        assert normalize_initial('A') == 'A'

    def test_lowercase_letter(self):
        assert normalize_initial('b') == 'B'

    def test_z_uppercase(self):
        assert normalize_initial('Z') == 'Z'

    def test_digit(self):
        assert normalize_initial('1') == '_'

    def test_symbol(self):
        assert normalize_initial('@') == '_'

    def test_empty_string(self):
        assert normalize_initial('') == '_'

    def test_chinese_char(self):
        assert normalize_initial('中') == '_'

    def test_space(self):
        assert normalize_initial(' ') == '_'


class TestGetArtistSortFields:
    """Tests for get_artist_sort_fields(name: str) -> tuple[str, str]"""

    def test_none(self):
        sort_name, initial = get_artist_sort_fields(None)
        assert sort_name == ''
        assert initial == '_'

    def test_empty_string(self):
        sort_name, initial = get_artist_sort_fields('')
        assert sort_name == ''
        assert initial == '_'

    def test_spaces_only(self):
        sort_name, initial = get_artist_sort_fields('   ')
        assert sort_name == ''
        assert initial == '_'

    def test_english_name(self):
        sort_name, initial = get_artist_sort_fields('Taylor Swift')
        assert sort_name == 'Taylor Swift'
        assert initial == 'T'

    def test_english_lowercase(self):
        sort_name, initial = get_artist_sort_fields('  test  ')
        assert sort_name == 'Test'
        assert initial == 'T'

    def test_chinese_name(self):
        sort_name, initial = get_artist_sort_fields('周杰伦')
        # pypinyin converts 周杰伦 to ['zhou', 'jie', 'lun']
        assert sort_name == 'Zhou Jie Lun'
        assert initial == 'Z'

    def test_chinese_single_char(self):
        sort_name, initial = get_artist_sort_fields('邓')
        # pypinyin converts 邓 to ['deng']
        assert 'Deng' in sort_name
        assert initial == 'D'
