# -*- encoding: utf-8 -*-
"""
tests/api/test_auth.py
Integration tests for /api/v1/auth/* endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.auth_service import AuthService
from app.core.db import get_db
from app.core.config import Settings
from app.core.deps import get_client_type, get_current_user
from app.schemas.token import ClientType
from app.schemas.user import CurrentUser


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_auth_service():
    svc = MagicMock(spec=AuthService)
    svc.authenticate_user = AsyncMock()
    svc.create_access_token = MagicMock(return_value='mock-access-token')
    svc.create_refresh_token = AsyncMock(return_value='mock-refresh-token')
    svc.get_device_token_jti = AsyncMock(return_value='device-jti')
    svc.refresh_session = AsyncMock(return_value=('new-access', 'new-refresh'))
    svc.revoke_token = AsyncMock()
    svc.get_password_hash = MagicMock(return_value='hashed-pw')
    return svc


@pytest.fixture
def mock_db_session():
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=0)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def client(mock_auth_service, mock_db_session):
    """AsyncClient with dependency overrides for auth endpoints."""

    async def _override_db():
        yield mock_db_session

    async def _override_settings():
        from app.core.config import Settings
        s = Settings()
        return s

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[AuthService] = lambda: mock_auth_service
    app.dependency_overrides[get_client_type] = lambda: ClientType.PUBLIC

    yield AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url='http://test',
    )

    app.dependency_overrides.clear()


# ===========================================================================
# POST /api/v1/auth/login
# ===========================================================================

class TestLogin:
    async def test_login_success(self, client, mock_auth_service):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth_service.authenticate_user.return_value = mock_user

        resp = await client.post('/api/v1/auth/login', json={
            'username': 'alice',
            'password': 'secret',
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body['code'] == 200
        assert body['data']['access_token'] == 'mock-access-token'
        assert body['data']['refresh_token'] == 'mock-refresh-token'

    async def test_login_invalid_credentials(self, client, mock_auth_service):
        mock_auth_service.authenticate_user.return_value = None

        resp = await client.post('/api/v1/auth/login', json={
            'username': 'alice',
            'password': 'wrong',
        })
        assert resp.status_code == 401

    async def test_login_reports_real_access_ttl(self, client, mock_auth_service, test_settings):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth_service.authenticate_user.return_value = mock_user

        resp = await client.post('/api/v1/auth/login', json={
            'username': 'alice',
            'password': 'secret',
        })
        assert resp.status_code == 200
        assert resp.json()['data']['expires_in'] == test_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    async def test_login_prefers_header_device_id(self, client, mock_auth_service):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth_service.authenticate_user.return_value = mock_user

        resp = await client.post(
            '/api/v1/auth/login',
            json={'username': 'alice', 'password': 'secret', 'device_id': 'body-dev'},
            headers={'X-Device-Id': 'header-dev'},
        )
        assert resp.status_code == 200
        assert mock_auth_service.create_refresh_token.await_args.args[2] == 'header-dev'

    async def test_login_access_token_uses_device_jti(self, client, mock_auth_service):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_auth_service.authenticate_user.return_value = mock_user

        resp = await client.post('/api/v1/auth/login', json={
            'username': 'alice',
            'password': 'secret',
        })
        assert resp.status_code == 200
        assert mock_auth_service.create_access_token.call_args.kwargs['jti'] == 'device-jti'


# ===========================================================================
# POST /api/v1/auth/register
# ===========================================================================

class TestRegister:
    async def test_register_first_user(self, client, mock_db_session, mock_auth_service):
        mock_db_session.scalar = AsyncMock(return_value=0)

        # Mock the User model validation that UserResponse.model_validate uses
        mock_user_db = MagicMock()
        mock_user_db.id = 1
        mock_user_db.username = 'newuser'
        mock_user_db.is_admin = True
        mock_user_db.created_at = '2025-01-01T00:00:00'

        # Make db.add capture the user, then make model_validate work
        with pytest.MonkeyPatch.context() as mp:
            # We need to intercept User creation and model_validate
            from app.api.v1 import auth as auth_module
            original_register = auth_module.register

            # Just mock model_validate to return a valid response
            from app.schemas.user import UserResponse
            mp.setattr(UserResponse, 'model_validate', classmethod(
                lambda cls, obj: cls(id=1, username='newuser', is_admin=True, created_at='2025-01-01T00:00:00')
            ))
            resp = await client.post('/api/v1/auth/register', json={
                'username': 'newuser',
                'password': 'secret',
                'is_admin': True,
            })

        assert resp.status_code == 200
        assert resp.json()['code'] == 200
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_awaited_once()

    async def test_register_blocked_after_first_user(self, client, mock_db_session):
        mock_db_session.scalar = AsyncMock(return_value=1)

        resp = await client.post('/api/v1/auth/register', json={
            'username': 'another',
            'password': 'secret',
        })
        assert resp.status_code == 403


# ===========================================================================
# POST /api/v1/auth/refresh
# ===========================================================================

class TestRefresh:
    async def test_refresh_success(self, client, mock_auth_service):
        resp = await client.post('/api/v1/auth/refresh', json={
            'refresh_token': 'old-refresh-token',
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body['data']['access_token'] == 'new-access'
        assert body['data']['refresh_token'] == 'new-refresh'

    async def test_refresh_invalid_token_returns_401(self, client, mock_auth_service):
        mock_auth_service.refresh_session.side_effect = ValueError('Invalid refresh token')
        resp = await client.post('/api/v1/auth/refresh', json={
            'refresh_token': 'bad-token',
        })
        assert resp.status_code == 401
        assert resp.json()['code'] == 20002

    async def test_refresh_transient_failure_is_retryable(self, client, mock_auth_service):
        """DB/网络等临时故障不能用 401 把用户踢到登录页"""
        mock_auth_service.refresh_session.side_effect = RuntimeError('db connection lost')
        resp = await client.post('/api/v1/auth/refresh', json={
            'refresh_token': 'old-refresh-token',
        })
        assert resp.status_code == 503
        assert resp.json()['code'] == 20010

    async def test_refresh_uses_body_device_id_as_fallback(self, client, mock_auth_service):
        await client.post('/api/v1/auth/refresh', json={
            'refresh_token': 'old-refresh-token',
            'device_id': 'body-dev',
        })
        assert mock_auth_service.refresh_session.await_args.kwargs['device_id'] == 'body-dev'

    async def test_refresh_prefers_header_device_id(self, client, mock_auth_service):
        await client.post(
            '/api/v1/auth/refresh',
            json={'refresh_token': 'old-refresh-token', 'device_id': 'body-dev'},
            headers={'X-Device-Id': 'header-dev'},
        )
        assert mock_auth_service.refresh_session.await_args.kwargs['device_id'] == 'header-dev'


# ===========================================================================
# GET /api/v1/auth/me
# ===========================================================================

class TestGetMe:
    async def test_me_success(self, client, mock_auth_service):
        # Override get_current_user for this test
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=5, is_admin=False, username='bob'
        )
        resp = await client.get('/api/v1/auth/me')
        assert resp.status_code == 200
        body = resp.json()
        assert body['data']['username'] == 'bob'
        assert body['data']['id'] == 5
