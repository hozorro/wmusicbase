# -*- encoding: utf-8 -*-
"""
tests/conftest.py
Shared fixtures for all tests.

CRITICAL: Environment variables must be set BEFORE any app.* import,
because app/core/config.py, app/core/db.py, app/utils/streaming.py
all execute side effects at module level.
"""

import os

# ---- Set env vars before any app.* import ----
os.environ.setdefault('DB_USER', 'wsonic')
os.environ.setdefault('DB_PASSWORD', 'kevsN4w*')
os.environ.setdefault('DB_HOST', '192.168.137.247')
os.environ.setdefault('DB_PORT', '5432')
os.environ.setdefault('DB_NAME', 'musictest')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-testing-only')
os.environ.setdefault('ACOUSTID_API_KEY', 'test-acoustid-key')

# ---- Now safe to import app modules ----
# Import deps first to resolve circular dependency (deps -> auth_service -> deps)
import app.core.deps  # noqa: F401
import pytest
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture(scope='session')
def test_settings():
    """Real Settings instance using test database env vars."""
    from app.core.config import Settings
    return Settings()


@pytest.fixture
def mock_db():
    """AsyncMock of AsyncSession with all common methods."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    db.scalar_one_or_none = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    db.close = AsyncMock()
    db.is_active = True
    db.is_closed = MagicMock(return_value=False)
    return db


@pytest.fixture
def mock_user():
    """Mock User object with standard attributes."""
    user = MagicMock()
    user.id = 1
    user.username = 'testuser'
    user.password_hash = ''  # will be set by test
    user.is_admin = False
    return user


@pytest.fixture
def mock_admin_user():
    """Mock admin User object."""
    admin = MagicMock()
    admin.id = 2
    admin.username = 'admin'
    admin.password_hash = ''
    admin.is_admin = True
    return admin


@pytest.fixture
def auth_service(mock_db, test_settings):
    """AuthService with mock db and test settings."""
    from app.services.auth_service import AuthService
    return AuthService(db=mock_db, settings=test_settings)


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear TTLCache and other module-level caches between tests."""
    yield
    try:
        from app.core.deps import _USER_CACHE
        _USER_CACHE.clear()
    except ImportError:
        pass
