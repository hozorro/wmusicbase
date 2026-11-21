# -*- encoding: utf-8 -*-
"""
Tests for app/services/auth_service.py
Methods: get_password_hash, verify_password, authenticate_user,
         create_access_token, create_refresh_token, verify_access_token,
         verify_refresh_token, refresh_with_rotation, revoke_token
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import timedelta, datetime, timezone
from jose import jwt, JWTError
from app.services.auth_service import pwd_context
from app.schemas.token import ClientType


class TestPasswordHashing:
    """Tests for get_password_hash and verify_password"""

    def test_hash_starts_with_bcrypt(self, auth_service):
        hashed = auth_service.get_password_hash('my_password')
        # bcrypt_sha256 hashes start with $bcrypt-sha256$
        assert '$bcrypt' in hashed

    def test_different_passwords_different_hashes(self, auth_service):
        h1 = auth_service.get_password_hash('password1')
        h2 = auth_service.get_password_hash('password2')
        assert h1 != h2

    def test_verify_correct_password(self, auth_service):
        hashed = auth_service.get_password_hash('test_password')
        assert auth_service.verify_password('test_password', hashed) is True

    def test_verify_wrong_password(self, auth_service):
        hashed = auth_service.get_password_hash('test_password')
        assert auth_service.verify_password('wrong_password', hashed) is False


class TestAuthenticateUser:
    """Tests for authenticate_user (async)"""

    async def test_user_exists_correct_password(self, auth_service, mock_db, mock_user):
        mock_user.password_hash = auth_service.get_password_hash('correct_pass')
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.authenticate_user('testuser', 'correct_pass')
        assert result is mock_user

    async def test_user_not_found(self, auth_service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.authenticate_user('nonexistent', 'pass')
        assert result is None

    async def test_wrong_password(self, auth_service, mock_db, mock_user):
        mock_user.password_hash = auth_service.get_password_hash('correct_pass')
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.authenticate_user('testuser', 'wrong_pass')
        assert result is None


class TestCreateAccessToken:
    """Tests for create_access_token"""

    def test_default_expiry(self, auth_service, test_settings):
        token = auth_service.create_access_token(1, 'player')
        payload = jwt.decode(token, test_settings.SECRET_KEY, algorithms=['HS256'])
        assert payload['sub'] == '1'
        assert payload['client_type'] == 'player'
        assert 'jti' in payload

    def test_custom_expiry(self, auth_service, test_settings):
        token = auth_service.create_access_token(1, 'admin', expires_delta=timedelta(hours=1))
        payload = jwt.decode(token, test_settings.SECRET_KEY, algorithms=['HS256'])
        assert 'exp' in payload

    def test_unique_jti(self, auth_service):
        t1 = auth_service.create_access_token(1, 'player')
        t2 = auth_service.create_access_token(1, 'player')
        # JTI should be different for each token
        assert t1 != t2


class TestCreateRefreshToken:
    """Tests for create_refresh_token (async)"""

    async def test_new_token_creation(self, auth_service, mock_db):
        # No existing token
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        raw_token = await auth_service.create_refresh_token(1, ClientType.PUBLIC, 'device-1')
        assert isinstance(raw_token, str)
        assert len(raw_token) > 0
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_sso_update_existing(self, auth_service, mock_db):
        # Existing token found
        existing = MagicMock()
        existing.refresh_token_hash = 'old_hash'
        existing.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        existing.is_revoked = True
        existing.last_used_at = None
        existing.access_token_jti = 'old_jti'

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=mock_result)

        raw_token = await auth_service.create_refresh_token(1, ClientType.PUBLIC, 'device-1')
        assert isinstance(raw_token, str)
        # Should update existing, not add new
        mock_db.add.assert_not_called()
        assert existing.is_revoked is False


class TestVerifyAccessToken:
    """Tests for verify_access_token (async)"""

    async def test_valid_token(self, auth_service, mock_db, test_settings):
        token = auth_service.create_access_token(42, 'player')
        # Mock: no revoked token found
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        payload = await auth_service.verify_access_token(token)
        assert payload['user_id'] == 42
        assert payload['client_type'] == 'player'
        assert 'jti' in payload

    async def test_expired_token(self, auth_service, mock_db):
        # Create token that's already expired
        token = auth_service.create_access_token(1, 'player', expires_delta=timedelta(seconds=-1))
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(JWTError):
            await auth_service.verify_access_token(token)

    async def test_invalid_signature(self, auth_service, mock_db):
        # Create token with different secret
        token = jwt.encode({'sub': '1', 'client_type': 'player', 'exp': datetime.now(timezone.utc) + timedelta(hours=1)}, 'wrong-secret', algorithm='HS256')
        mock_result = MagicMock()
        mock_result.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(JWTError):
            await auth_service.verify_access_token(token)

    async def test_revoked_token(self, auth_service, mock_db, test_settings):
        token = auth_service.create_access_token(1, 'player')
        # Mock: revoked token found
        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock()  # revoked record
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(JWTError):
            await auth_service.verify_access_token(token)


class TestVerifyRefreshToken:
    """Tests for verify_refresh_token (async)"""

    async def test_valid_refresh_token(self, auth_service, mock_db):
        raw_token = 'test-refresh-token'
        token_hash = pwd_context.hash(raw_token)

        token_rec = MagicMock()
        token_rec.refresh_token_hash = token_hash
        token_rec.last_used_at = None

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [token_rec]
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.verify_refresh_token(ClientType.PUBLIC, raw_token)
        assert result is token_rec
        mock_db.commit.assert_called_once()

    async def test_invalid_refresh_token(self, auth_service, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await auth_service.verify_refresh_token(ClientType.PUBLIC, 'invalid-token')
        assert result is None


class TestRefreshSession:
    """方案A：刷新只签发 access token，refresh token 保持有效"""

    def _mock_token_record(self, mock_db, raw_refresh):
        token_rec = MagicMock()
        token_rec.refresh_token_hash = pwd_context.hash(raw_refresh)
        token_rec.user_id = 1
        token_rec.last_used_at = None
        token_rec.is_revoked = False
        token_rec.access_token_jti = 'device-jti-1'
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [token_rec]
        mock_db.execute = AsyncMock(return_value=mock_result)
        return token_rec

    async def test_valid_refresh_keeps_refresh_token(self, auth_service, mock_db):
        raw_refresh = 'test-refresh-token'
        token_rec = self._mock_token_record(mock_db, raw_refresh)

        with patch.object(auth_service, 'create_refresh_token', new_callable=AsyncMock) as create_mock:
            new_access, new_refresh = await auth_service.refresh_session(
                ClientType.PUBLIC, raw_refresh, 'device-1'
            )
            create_mock.assert_not_awaited()

        assert isinstance(new_access, str)
        assert new_refresh == raw_refresh
        assert token_rec.is_revoked is False

    async def test_repeated_refresh_with_same_token_succeeds(self, auth_service, mock_db):
        """响应丢失后重试同一 token 必须成功，不能因轮换被作废"""
        raw_refresh = 'test-refresh-token'
        token_rec = self._mock_token_record(mock_db, raw_refresh)

        first = await auth_service.refresh_session(ClientType.PUBLIC, raw_refresh, 'device-1')
        second = await auth_service.refresh_session(ClientType.PUBLIC, raw_refresh, 'device-1')

        assert first[1] == second[1] == raw_refresh
        assert token_rec.is_revoked is False

    async def test_invalid_refresh_raises(self, auth_service, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match='Invalid refresh token'):
            await auth_service.refresh_session(ClientType.PUBLIC, 'bad-token')

    async def test_db_error_is_not_swallowed_as_invalid_token(self, auth_service, mock_db):
        """DB 临时故障不能伪装成「凭证失效」"""
        from sqlalchemy.exc import SQLAlchemyError
        mock_db.execute = AsyncMock(side_effect=SQLAlchemyError('db down'))

        with pytest.raises(SQLAlchemyError):
            await auth_service.verify_refresh_token(ClientType.PUBLIC, 'some-token')


class TestRevokeToken:
    """Tests for revoke_token (async)"""

    async def test_single_device(self, auth_service, mock_db):
        await auth_service.revoke_token(1, ClientType.PUBLIC, device_id='dev-1')
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_all_devices(self, auth_service, mock_db):
        await auth_service.revoke_token(1, ClientType.PUBLIC, all_devices=True)
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    async def test_missing_device_id_only_revokes_default_device(self, auth_service, mock_db):
        """不带设备头登出不能连带撤销该用户所有设备"""
        await auth_service.revoke_token(1, ClientType.PUBLIC, device_id=None)
        stmt = mock_db.execute.await_args.args[0]
        assert 'device_id' in str(stmt)


class TestRefreshTokenDefaults:
    async def test_missing_device_id_does_not_violate_not_null(self, auth_service, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        await auth_service.create_refresh_token(1, ClientType.PUBLIC, None)

        added = mock_db.add.call_args.args[0]
        assert added.device_id == 'unknown-device'


class TestAccessTokenJti:
    """JWT jti 必须与设备行关联，logout 才能真正撤销 access token"""

    async def test_refresh_issues_token_with_device_jti(self, auth_service, mock_db, test_settings):
        raw_refresh = 'test-refresh-token'
        token_rec = MagicMock()
        token_rec.refresh_token_hash = pwd_context.hash(raw_refresh)
        token_rec.user_id = 1
        token_rec.last_used_at = None
        token_rec.is_revoked = False
        token_rec.access_token_jti = 'device-jti-1'
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [token_rec]
        mock_db.execute = AsyncMock(return_value=mock_result)

        new_access, _ = await auth_service.refresh_session(ClientType.PUBLIC, raw_refresh, 'device-1')
        payload = jwt.decode(new_access, test_settings.SECRET_KEY, algorithms=['HS256'])
        assert payload['jti'] == 'device-jti-1'

    async def test_login_jti_matches_device_record(self, auth_service, mock_db, test_settings):
        created = {}
        mock_db.add = MagicMock(side_effect=lambda obj: created.setdefault('token', obj))
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        await auth_service.create_refresh_token(1, ClientType.PUBLIC, 'device-1')
        row_jti = created['token'].access_token_jti

        jti_result = MagicMock()
        jti_result.scalar_one_or_none.return_value = row_jti
        mock_db.execute = AsyncMock(return_value=jti_result)
        assert await auth_service.get_device_token_jti(1, ClientType.PUBLIC, 'device-1') == row_jti

        access = auth_service.create_access_token(1, ClientType.PUBLIC, jti=row_jti)
        payload = jwt.decode(access, test_settings.SECRET_KEY, algorithms=['HS256'])
        assert payload['jti'] == row_jti

    async def test_revoked_device_row_rejects_access_token(self, auth_service, mock_db, test_settings):
        token = auth_service.create_access_token(1, 'player', jti='device-jti-1')
        mock_result = MagicMock()
        mock_result.first.return_value = MagicMock()  # is_revoked=True 的设备行
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(JWTError):
            await auth_service.verify_access_token(token)

        stmt = mock_db.execute.await_args.args[0]
        assert 'device-jti-1' in stmt.compile().params.values()
