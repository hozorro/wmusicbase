# -*- encoding: utf-8 -*-
"""Upload policy: extension + Content-Type must both be allowed."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BusinessException
from app.utils.audio_formats import is_allowed_upload


def _upload(ctype, filename):
    f = MagicMock()
    f.content_type = ctype
    f.filename = filename
    f.read = AsyncMock(return_value=b'audio-bytes')
    f.close = AsyncMock()
    return f


EXTS = ['.mp3', '.flac', '.m4a']


def test_m4a_common_content_types_are_accepted():
    for ctype in ('audio/mp4', 'audio/x-m4a', 'audio/mp4a-latm',
                  'audio/aac', 'application/octet-stream'):
        assert is_allowed_upload('07. Take It All.m4a', ctype, EXTS) is True


def test_extension_must_be_in_settings_whitelist():
    assert is_allowed_upload('x.m4b', 'audio/mp4', EXTS) is False
    assert is_allowed_upload('x.m4p', 'audio/mp4', EXTS) is False
    assert is_allowed_upload('x.mp3', 'audio/mpeg', EXTS) is True


def test_wrong_mime_is_rejected_even_with_valid_suffix():
    assert is_allowed_upload('x.m4a', 'image/png', EXTS) is False
    assert is_allowed_upload('x.m4a', 'text/plain', EXTS) is False


class TestUploadEndpoint:
    @pytest.mark.asyncio
    async def test_accepts_m4a(self):
        from app.api.v1.admin import upload
        f = _upload('audio/mp4', '07. Take It All.m4a')
        service = MagicMock()
        service.save_temp_file = AsyncMock()

        await upload.upload_file(f, None, service)

        service.save_temp_file.assert_awaited_once_with(b'audio-bytes', '07. Take It All.m4a')

    @pytest.mark.asyncio
    async def test_rejects_txt_with_audio_mpeg(self):
        from app.api.v1.admin import upload
        f = _upload('audio/mpeg', 'x.txt')
        service = MagicMock()
        service.save_temp_file = AsyncMock()

        with pytest.raises(BusinessException):
            await upload.upload_file(f, None, service)

        service.save_temp_file.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_m4a_with_image_mime(self):
        from app.api.v1.admin import upload
        f = _upload('image/png', 'x.m4a')
        service = MagicMock()
        service.save_temp_file = AsyncMock()

        with pytest.raises(BusinessException):
            await upload.upload_file(f, None, service)

        service.save_temp_file.assert_not_awaited()
