# -*- encoding: utf-8 -*-
"""
Tests for app/utils/metadata.py
Functions: decode_tag_value, extract_cover_art_hash, parse_metadata, read_apev2_tags
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
from app.utils.metadata import decode_tag_value, extract_cover_art_hash, read_apev2_tags


class TestDecodeTagValue:
    """Tests for decode_tag_value(raw_value, encoding) -> str"""

    def test_encoding_latin1_ascii(self):
        # encoding=0 (LATIN1 -> gb18030): ASCII text survives
        result = decode_tag_value('Hello', 0)
        assert result == 'Hello'

    def test_encoding_utf16_bytes(self):
        # encoding=1 (UTF-16)
        data = 'Hi'.encode('utf-16')
        result = decode_tag_value(data, 1)
        assert 'Hi' in result

    def test_encoding_utf16be_bytes(self):
        # encoding=2 (UTF-16BE)
        data = 'Hi'.encode('utf-16be')
        result = decode_tag_value(data, 2)
        assert 'Hi' in result

    def test_encoding_utf8_bytes(self):
        # encoding=3 (UTF-8)
        result = decode_tag_value(b'Hello', 3)
        assert result == 'Hello'

    def test_encoding_utf8_strips_whitespace(self):
        result = decode_tag_value(b'  Hello  ', 3)
        assert result == 'Hello'

    def test_encoding_unknown_fallback(self):
        # encoding=99 (unknown) -> str(raw_value)
        result = decode_tag_value('test', 99)
        assert result == 'test'


class TestExtractCoverArtHash:
    """Tests for extract_cover_art_hash(file_path) -> str | None"""

    @patch('app.utils.metadata.MutagenFile')
    def test_mp3_with_apic(self, mock_mutagen):
        mock_audio = MagicMock()
        mock_tags = MagicMock()
        mock_tags.keys.return_value = ['APIC:Cover']
        mock_tags.__getitem__ = MagicMock(return_value=MagicMock(data=b'cover_data'))
        mock_audio.tags = mock_tags
        mock_mutagen.return_value = mock_audio

        result = extract_cover_art_hash(Path('/fake/song.mp3'))
        assert isinstance(result, str)
        assert len(result) == 40  # SHA1 hex

    @patch('app.utils.metadata.MutagenFile')
    def test_flac_with_picture(self, mock_mutagen):
        mock_audio = MagicMock()
        mock_audio.tags = None  # no tags attribute for FLAC branch
        mock_picture = MagicMock()
        mock_picture.data = b'flac_cover_data'
        mock_audio.pictures = [mock_picture]
        mock_mutagen.return_value = mock_audio

        result = extract_cover_art_hash(Path('/fake/song.flac'))
        assert isinstance(result, str)
        assert len(result) == 40

    @patch('app.utils.metadata.MutagenFile')
    def test_no_cover(self, mock_mutagen):
        mock_audio = MagicMock()
        mock_tags = MagicMock()
        mock_tags.keys.return_value = ['TIT2']  # no APIC keys
        mock_audio.tags = mock_tags
        mock_mutagen.return_value = mock_audio

        result = extract_cover_art_hash(Path('/fake/song.mp3'))
        assert result is None

    @patch('app.utils.metadata.MutagenFile')
    def test_parse_error(self, mock_mutagen):
        mock_mutagen.side_effect = Exception('Parse error')
        result = extract_cover_art_hash(Path('/fake/song.mp3'))
        assert result is None


class TestReadApev2Tags:
    """Tests for read_apev2_tags(file_path) -> dict[str, list[str]]

    回归用例：该函数曾因缺少 APEv2 导入而恒返回 {}。
    """

    @patch('app.utils.metadata.APEv2')
    def test_parses_known_keys(self, mock_apev2):
        tag = MagicMock()
        tag.__getitem__ = MagicMock(side_effect=lambda k: {
            'Title': 'Song',
            'Artist': ['A', ' B '],
            'Album': 'AL',
            'Year': '2020-01-01',
            'Genre': 'Rock',
        }[k])
        mock_apev2.return_value = tag

        result = read_apev2_tags(Path('/fake/song.mp3'))

        assert result['title'] == ['Song']
        assert result['artists'] == ['A', 'B']  # 元素被 strip
        assert result['album'] == ['AL']
        assert result['year'] == ['2020-01-01']
        assert result['genres'] == ['Rock']

    @patch('app.utils.metadata.APEv2')
    def test_missing_keys_are_skipped(self, mock_apev2):
        tag = MagicMock()
        tag.__getitem__ = MagicMock(side_effect=KeyError('Title'))
        mock_apev2.return_value = tag

        assert read_apev2_tags(Path('/fake/song.mp3')) == {}

    @patch('app.utils.metadata.APEv2')
    def test_no_apev2_header_returns_empty(self, mock_apev2):
        mock_apev2.side_effect = Exception('no APEv2 header')

        assert read_apev2_tags(Path('/fake/song.mp3')) == {}
