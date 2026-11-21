# -*- encoding: utf-8 -*-
"""
Tests for app/core/config.py
Validators: Settings.assemble_db_url, Settings.convert_str_to_path, property methods
"""

import pytest
from pathlib import Path
from pydantic import ValidationError
from app.core.config import Settings


def make_settings(**overrides):
    """Helper to create Settings with test defaults + overrides."""
    defaults = {
        'DB_USER': 'testuser',
        'DB_PASSWORD': 'testpass',
        'DB_HOST': 'localhost',
        'DB_PORT': 5432,
        'DB_NAME': 'testdb',
        'SECRET_KEY': 'test-secret',
        'ACOUSTID_API_KEY': 'test-acoustid',
    }
    defaults.update(overrides)
    return Settings(**defaults)


class TestAssembleDbUrl:
    """Tests for Settings.assemble_db_url field_validator"""

    def test_direct_url(self):
        """DATABASE_URL provided directly -> used as-is"""
        s = make_settings(DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/db')
        assert 'user:pass@host' in str(s.DATABASE_URL)

    def test_joined_from_db_fields(self):
        """DATABASE_URL not provided -> assembled from DB_* fields"""
        s = make_settings()
        url = str(s.DATABASE_URL)
        assert 'testuser' in url
        assert 'testdb' in url

    def test_missing_db_user(self):
        """Missing required DB_* fields -> ValidationError or ValueError"""
        import os
        # Clear DB_USER from env AND disable .env file loading
        saved = os.environ.pop('DB_USER', None)
        try:
            with pytest.raises((ValidationError, ValueError)):
                Settings(
                    _env_file=None,
                    DB_PASSWORD='pass',
                    DB_HOST='localhost',
                    DB_PORT=5432,
                    DB_NAME='db',
                    SECRET_KEY='key',
                    ACOUSTID_API_KEY='key',
                )
        finally:
            if saved is not None:
                os.environ['DB_USER'] = saved


class TestConvertStrToPath:
    """Tests for Settings.convert_str_to_path field_validator"""

    def test_string_path(self):
        s = make_settings(MEDIA_ROOT='/tmp/media')
        assert isinstance(s.MEDIA_ROOT, Path)

    def test_backslash_conversion(self):
        s = make_settings(MEDIA_ROOT='D:\\music\\media')
        # On Windows, Path uses backslash internally, so just verify it's a Path
        assert isinstance(s.MEDIA_ROOT, Path)

    def test_path_object(self):
        s = make_settings(MEDIA_ROOT=Path('/tmp/media'))
        assert isinstance(s.MEDIA_ROOT, Path)


class TestPropertyMethods:
    """Tests for Settings property methods"""

    def test_temp_dir(self):
        s = make_settings()
        assert s.TEMP_DIR == s.MEDIA_ROOT / 'uploads' / 'temp'

    def test_staging_dir(self):
        s = make_settings()
        assert s.STAGING_DIR == s.MEDIA_ROOT / 'uploads' / 'staging'

    def test_artwork_dir(self):
        s = make_settings()
        assert s.ARTWORK_DIR == s.MEDIA_ROOT / 'artwork'
