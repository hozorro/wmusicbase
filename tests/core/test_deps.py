# -*- encoding: utf-8 -*-
"""
tests/core/test_deps.py
Tests for dependency injection functions in app/core/deps.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.deps import get_client_type, get_current_user, require_admin, _USER_CACHE
from app.core.exceptions import BusinessException
from app.schemas.token import ClientType
from app.schemas.user import CurrentUser


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_request(headers=None, path='/'):
    req = MagicMock()
    req.headers = headers or {}
    req.url = MagicMock()
    req.url.path = path
    req.state = MagicMock()
    return req


# ===========================================================================
# get_client_type
# ===========================================================================

class TestGetClientType:
    async def test_header_admin(self):
        req = _mock_request(headers={'X-Client-Type': 'admin'})
        result = await get_client_type(req)
        assert result == ClientType.ADMIN

    async def test_header_player(self):
        req = _mock_request(headers={'X-Client-Type': 'player'})
        result = await get_client_type(req)
        assert result == ClientType.PUBLIC

    async def test_header_app(self):
        req = _mock_request(headers={'X-Client-Type': 'app'})
        result = await get_client_type(req)
        assert result == ClientType.APP

    async def test_header_web(self):
        req = _mock_request(headers={'X-Client-Type': 'web'})
        result = await get_client_type(req)
        assert result == ClientType.WEB

    async def test_invalid_header_fallback_to_admin_url(self):
        req = _mock_request(headers={'X-Client-Type': 'invalid'}, path='/api/v1/admin/scan')
        result = await get_client_type(req)
        assert result == ClientType.ADMIN

    async def test_no_header_admin_url(self):
        req = _mock_request(path='/api/v1/admin/backup')
        result = await get_client_type(req)
        assert result == ClientType.ADMIN

    async def test_no_header_music_url(self):
        req = _mock_request(path='/api/v1/music/track')
        result = await get_client_type(req)
        assert result == ClientType.PUBLIC

    async def test_admin_path_contains_admin(self):
        req = _mock_request(path='/some/admin/endpoint')
        result = await get_client_type(req)
        assert result == ClientType.ADMIN

    async def test_no_header_no_matching_url_raises(self):
        req = _mock_request(path='/api/v1/auth/login')
        with pytest.raises(BusinessException) as exc_info:
            await get_client_type(req)
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == 10001


# ===========================================================================
# get_current_user
# ===========================================================================

class TestGetCurrentUser:
    async def test_no_token_returns_credentials_exception(self):
        """When token is None/empty, raise 401 BusinessException."""
        with pytest.raises(BusinessException) as exc_info:
            await get_current_user(
                token=None,
                db=AsyncMock(),
                client_type=ClientType.PUBLIC,
                service=AsyncMock(),
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == 20004

    async def test_valid_token_returns_current_user(self):
        mock_service = AsyncMock()
        mock_service.verify_access_token.return_value = {
            'user_id': 10,
            'client_type': ClientType.PUBLIC,
        }
        mock_user = MagicMock()
        mock_user.id = 10
        mock_user.is_admin = False
        mock_user.username = 'alice'
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        # Clear cache first
        _USER_CACHE.clear()

        result = await get_current_user(
            token='valid-token',
            db=mock_db,
            client_type=ClientType.PUBLIC,
            service=mock_service,
        )
        assert isinstance(result, CurrentUser)
        assert result.id == 10
        assert result.username == 'alice'

    async def test_client_type_mismatch_raises_403(self):
        mock_service = AsyncMock()
        mock_service.verify_access_token.return_value = {
            'user_id': 10,
            'client_type': ClientType.ADMIN,
        }
        # BusinessException is re-raised as-is, status code kept
        with pytest.raises(BusinessException) as exc_info:
            await get_current_user(
                token='token',
                db=AsyncMock(),
                client_type=ClientType.PUBLIC,
                service=mock_service,
            )
        assert exc_info.value.status_code == 403
        assert 'mismatch' in exc_info.value.msg

    async def test_missing_user_id_raises_403(self):
        mock_service = AsyncMock()
        mock_service.verify_access_token.return_value = {
            'client_type': ClientType.PUBLIC,
            # no user_id
        }
        with pytest.raises(BusinessException) as exc_info:
            await get_current_user(
                token='token',
                db=AsyncMock(),
                client_type=ClientType.PUBLIC,
                service=mock_service,
            )
        assert exc_info.value.status_code == 403

    async def test_cached_user_returned(self):
        """User in TTLCache should be returned directly without DB query."""
        cached_user = CurrentUser(id=20, is_admin=True, username='bob')
        _USER_CACHE[20] = cached_user

        mock_service = AsyncMock()
        mock_service.verify_access_token.return_value = {
            'user_id': 20,
            'client_type': ClientType.ADMIN,
        }
        mock_db = AsyncMock()

        result = await get_current_user(
            token='token',
            db=mock_db,
            client_type=ClientType.ADMIN,
            service=mock_service,
        )
        assert result is cached_user
        mock_db.execute.assert_not_awaited()

    async def test_user_not_found_in_db_raises_401(self):
        mock_service = AsyncMock()
        mock_service.verify_access_token.return_value = {
            'user_id': 999,
            'client_type': ClientType.PUBLIC,
        }
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        _USER_CACHE.clear()

        with pytest.raises(BusinessException) as exc_info:
            await get_current_user(
                token='token',
                db=mock_db,
                client_type=ClientType.PUBLIC,
                service=mock_service,
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == 20005

    async def test_invalid_token_raises_401(self):
        mock_service = AsyncMock()
        mock_service.verify_access_token.side_effect = Exception('expired')

        with pytest.raises(BusinessException) as exc_info:
            await get_current_user(
                token='bad-token',
                db=AsyncMock(),
                client_type=ClientType.PUBLIC,
                service=mock_service,
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == 20008

    async def test_db_failure_during_user_lookup_is_retryable(self):
        """DB 抖动不能伪装成 401，否则前端会把用户踢下线"""
        from sqlalchemy.exc import SQLAlchemyError
        mock_service = AsyncMock()
        mock_service.verify_access_token.return_value = {
            'user_id': 10,
            'client_type': ClientType.PUBLIC,
        }
        mock_db = AsyncMock()
        mock_db.execute.side_effect = SQLAlchemyError('db down')
        _USER_CACHE.clear()

        with pytest.raises(BusinessException) as exc_info:
            await get_current_user(
                token='token',
                db=mock_db,
                client_type=ClientType.PUBLIC,
                service=mock_service,
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.code == 20010

    async def test_db_failure_during_token_verification_is_retryable(self):
        from sqlalchemy.exc import SQLAlchemyError
        mock_service = AsyncMock()
        mock_service.verify_access_token.side_effect = SQLAlchemyError('db down')

        with pytest.raises(BusinessException) as exc_info:
            await get_current_user(
                token='token',
                db=AsyncMock(),
                client_type=ClientType.PUBLIC,
                service=mock_service,
            )
        assert exc_info.value.status_code == 503
        assert exc_info.value.code == 20010


# ===========================================================================
# require_admin
# ===========================================================================

class TestRequireAdmin:
    async def test_admin_user_admin_client_passes(self):
        user = CurrentUser(id=1, is_admin=True, username='admin')
        req = _mock_request()
        result = await require_admin(
            request=req,
            current_user=user,
            client_type=ClientType.ADMIN,
        )
        assert result is user
        assert req.state.user_id == 1

    async def test_non_admin_raises_403(self):
        user = CurrentUser(id=2, is_admin=False, username='user')
        req = _mock_request()
        with pytest.raises(BusinessException) as exc_info:
            await require_admin(
                request=req,
                current_user=user,
                client_type=ClientType.ADMIN,
            )
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == 20009

    async def test_admin_user_non_admin_client_raises_403(self):
        user = CurrentUser(id=1, is_admin=True, username='admin')
        req = _mock_request()
        with pytest.raises(BusinessException) as exc_info:
            await require_admin(
                request=req,
                current_user=user,
                client_type=ClientType.PUBLIC,
            )
        assert exc_info.value.status_code == 403
