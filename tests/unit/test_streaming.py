# -*- encoding: utf-8 -*-
"""
Tests for app/utils/streaming.py
Functions: parse_range, signer sign/unsign
"""

import pytest
from itsdangerous import BadSignature
from app.core.exceptions import BusinessException
from app.utils.streaming import parse_range, signer


class TestParseRange:
    """Tests for parse_range(range_header, file_size) -> (start, end)"""

    def test_standard_range(self):
        assert parse_range('bytes=0-499', 1000) == (0, 499)

    def test_second_half(self):
        assert parse_range('bytes=500-999', 1000) == (500, 999)

    def test_open_end(self):
        # bytes=500- -> end defaults to file_size-1
        assert parse_range('bytes=500-', 1000) == (500, 999)

    def test_single_byte(self):
        assert parse_range('bytes=0-0', 1000) == (0, 0)

    def test_full_file(self):
        assert parse_range('bytes=0-999', 1000) == (0, 999)

    def test_end_beyond_file_size(self):
        with pytest.raises(BusinessException) as exc_info:
            parse_range('bytes=0-1000', 1000)
        assert exc_info.value.status_code == 416
        assert exc_info.value.code == 30307

    def test_start_greater_than_end(self):
        with pytest.raises(BusinessException) as exc_info:
            parse_range('bytes=500-499', 1000)
        assert exc_info.value.status_code == 416
        assert exc_info.value.code == 30307

    def test_invalid_format(self):
        with pytest.raises(BusinessException) as exc_info:
            parse_range('invalid', 1000)
        assert exc_info.value.status_code == 416
        assert exc_info.value.code == 30307

    def test_suffix_range(self):
        # bytes=-500 -> start_str='', end_str='500' -> start=0, end=500
        assert parse_range('bytes=-500', 1000) == (0, 500)


class TestAudioMime:
    """DEBUG streaming must not fall back to audio/mpeg for m4a on hosts without a registry entry."""

    def test_stream_module_uses_explicit_mime(self):
        from app.api.v1 import stream
        assert stream.audio_mime_for('x.m4a') == 'audio/mp4'
        assert stream.audio_mime_for('x.M4A') == 'audio/mp4'
        assert stream.audio_mime_for('x.mp3') == 'audio/mpeg'


class TestSigner:
    """Tests for TimestampSigner sign/unsign"""

    def test_sign_unsign_roundtrip(self):
        signed = signer.sign('track_123')
        result = signer.unsign(signed)
        assert result == b'track_123'

    def test_tampered_signature(self):
        signed = signer.sign('track_123')
        tampered = signed + b'x'
        with pytest.raises(BadSignature):
            signer.unsign(tampered)
