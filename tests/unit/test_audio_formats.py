# -*- encoding: utf-8 -*-
"""Tests for app/utils/audio_formats.py — centralized format knowledge."""

from unittest.mock import MagicMock

import pytest
from mutagen.mp4 import MP4Cover  # pyright: ignore[reportPrivateImportUsage]

from app.utils.audio_formats import (
    ALLOWED_UPLOAD_CONTENT_TYPES,
    AUDIO_MIME_BY_SUFFIX,
    MP4_SUFFIXES,
    _mp4_cover_format,
    audio_file_type,
    audio_mime_for,
    is_allowed_upload,
    mp4_cover_bytes,
    read_mp4_freeform,
    write_mp4_metadata,
)


class TestAudioFileType:
    @pytest.mark.parametrize('name,expected', [
        ('a.mp3', 'mp3'), ('a.MP3', 'mp3'),
        ('a.flac', 'flac'), ('a.FLAC', 'flac'),
        ('a.m4a', 'm4a'), ('a.M4A', 'm4a'),
        ('a.txt', 'NA'), ('a', 'NA'),
    ])
    def test_file_type(self, name, expected):
        assert audio_file_type(name) == expected

    def test_mp4_suffixes(self):
        assert MP4_SUFFIXES == {'.m4a'}


class TestAudioMime:
    @pytest.mark.parametrize('name,expected', [
        ('a.m4a', 'audio/mp4'), ('a.M4A', 'audio/mp4'),
        ('a.mp4', 'audio/mp4'), ('a.mp3', 'audio/mpeg'), ('a.flac', 'audio/flac'),
    ])
    def test_known_suffixes(self, name, expected):
        assert audio_mime_for(name) == expected
        assert AUDIO_MIME_BY_SUFFIX.get(name[name.rfind('.'):].lower()) == expected

    def test_unknown_suffix_returns_none(self):
        assert audio_mime_for('a.txt') is None


class TestIsAllowedUpload:
    @pytest.mark.parametrize('filename,ctype,allowed', [
        ('x.m4a', 'audio/mp4', True),
        ('x.m4a', 'audio/x-m4a', True),
        ('x.m4a', 'audio/mp4a-latm', True),
        ('x.m4a', 'audio/aac', True),
        ('x.m4a', 'application/octet-stream', True),
        ('x.M4A', 'audio/mp4', True),
        ('x.mp3', 'audio/mpeg', True),
        ('x.flac', 'audio/flac', True),
        ('x.txt', 'audio/mpeg', False),
        ('x.exe', 'audio/mp4', False),
        ('x.m4a', 'image/png', False),
        ('x.m4a', 'audio/mp4; charset=binary', True),
        (None, 'audio/mp4', False),
        ('x.m4a', None, False),
    ])
    def test_truth_table(self, filename, ctype, allowed):
        exts = ['.mp3', '.flac', '.m4a']
        assert is_allowed_upload(filename, ctype, exts) is allowed

    def test_stricter_whitelist_is_respected(self):
        assert is_allowed_upload('x.m4a', 'audio/mp4', ['.mp3']) is False

    def test_allowed_content_types_are_explicit(self):
        assert 'audio/mp4' in ALLOWED_UPLOAD_CONTENT_TYPES
        assert 'application/octet-stream' in ALLOWED_UPLOAD_CONTENT_TYPES


class TestMp4CoverBytes:
    def test_jpeg(self):
        audio = MagicMock()
        audio.tags = {'covr': [MP4Cover(b'\xff\xd8\xffdata', MP4Cover.FORMAT_JPEG)]}
        assert mp4_cover_bytes(audio) == b'\xff\xd8\xffdata'

    def test_png(self):
        audio = MagicMock()
        audio.tags = {'covr': [MP4Cover(b'\x89PNG\r\n\x1a\ndata', MP4Cover.FORMAT_PNG)]}
        cover = mp4_cover_bytes(audio)
        assert cover is not None
        assert cover.startswith(b'\x89PNG')

    def test_no_tags_or_no_covr(self):
        audio = MagicMock()
        audio.tags = None
        assert mp4_cover_bytes(audio) is None
        audio.tags = {'title': ['x']}
        assert mp4_cover_bytes(audio) is None

    def test_magicmock_tags_do_not_yield_false_cover(self):
        audio = MagicMock()
        audio.tags = MagicMock()  # .get('covr') returns a MagicMock, must be ignored
        assert mp4_cover_bytes(audio) is None

    def test_cover_format(self):
        assert _mp4_cover_format(b'\x89PNG\r\n\x1a\nx') == MP4Cover.FORMAT_PNG
        assert _mp4_cover_format(b'\xff\xd8\xffx') == MP4Cover.FORMAT_JPEG
        assert _mp4_cover_format(b'unknown') == MP4Cover.FORMAT_JPEG


class TestReadMp4Freeform:
    def test_reads_itunes_freeform_atoms(self, monkeypatch):
        audio = MagicMock()
        audio.tags = {
            '----:com.apple.iTunes:Acoustid Id': [b'cid-123'],
            '----:com.apple.iTunes:MusicBrainz Artist Id': [b'aid-1', b'aid-2'],
            '----:com.apple.iTunes:MusicBrainz Album Id': [b'alid-1'],
        }
        monkeypatch.setattr('app.utils.audio_formats.MP4', lambda _p: audio)

        result = read_mp4_freeform('x.m4a')

        assert result['acoustid_id'] == 'cid-123'
        assert result['mb_artistids'] == ['aid-1', 'aid-2']
        assert result['mb_albumid'] == 'alid-1'
        assert 'mb_trackid' not in result

    def test_missing_or_broken_file_returns_empty(self, monkeypatch):
        def boom(_p):
            raise OSError('bad file')
        monkeypatch.setattr('app.utils.audio_formats.MP4', boom)
        assert read_mp4_freeform('x.m4a') == {}


class TestWriteMp4Metadata:
    def test_writes_atoms_freeform_and_cover(self, monkeypatch):
        audio = MagicMock()
        tags = {}
        audio.tags = tags
        monkeypatch.setattr('app.utils.audio_formats.MP4', lambda _p: audio)

        jpeg = b'\xff\xd8\xff' + b'cover-data'
        write_mp4_metadata('x.m4a', {
            'title': 'New Title',
            'artists': ['A', 'B'],
            'album': 'Album',
            'albumartist': ['AA'],
            'year': 2011,
            'genres': ['Pop'],
            'acoustid_id': 'cid-1',
            'mb_artistids': ['aid-1'],
            'cover_art_data': jpeg,
        })

        assert tags['©nam'] == ['New Title']
        assert tags['©ART'] == ['A', 'B']
        assert tags['©alb'] == ['Album']
        assert tags['aART'] == ['AA']
        assert tags['©day'] == ['2011']
        assert tags['©gen'] == ['Pop']
        assert tags['----:com.apple.iTunes:Acoustid Id'] == [b'cid-1']
        assert tags['----:com.apple.iTunes:MusicBrainz Artist Id'] == [b'aid-1']
        assert isinstance(tags['covr'][0], MP4Cover)
        assert tags['covr'][0].imageformat == MP4Cover.FORMAT_JPEG
        assert bytes(tags['covr'][0]) == jpeg
        assert 'trkn' not in tags and 'disk' not in tags
        audio.save.assert_called_once_with()

    def test_png_cover_uses_png_format(self, monkeypatch):
        audio = MagicMock()
        tags = {}
        audio.tags = tags
        monkeypatch.setattr('app.utils.audio_formats.MP4', lambda _p: audio)

        png = b'\x89PNG\r\n\x1a\n' + b'data'
        write_mp4_metadata('x.m4a', {'cover_art_data': png})

        assert tags['covr'][0].imageformat == MP4Cover.FORMAT_PNG

    def test_adds_tags_when_absent(self, monkeypatch):
        audio = MagicMock()
        audio.tags = None
        created = {}
        audio.add_tags.side_effect = lambda: setattr(audio, 'tags', created)
        monkeypatch.setattr('app.utils.audio_formats.MP4', lambda _p: audio)

        write_mp4_metadata('x.m4a', {'title': 'T'})

        audio.add_tags.assert_called_once_with()
        assert created['©nam'] == ['T']
