# -*- encoding: utf-8 -*-
'''
@File      :   auth_service.py
@Time      :   2026/03/02 12:09:22
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   authorization service
'''


import secrets
from jose import jwt, JWTError, ExpiredSignatureError
from passlib.context import CryptContext
from sqlalchemy import select, update
from datetime import datetime, timedelta, timezone
from app.core.deps import DbDep, SettingsDep
from app.models.user import User, UserToken
from app.schemas.token import ClientType

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")

class AuthService:
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    # ========= password management =============
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)
    
    # ========= authentication =============
    async def authenticate_user(self, username: str, password: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user or not self.verify_password(password, user.password_hash):
            return None
        return user
    
    # ========= token generation ==========
    def create_access_token(self, user_id: int, client_type: str, expires_delta: timedelta | None = None) -> str:
        '''create access token (JWT)'''
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode = {
            "sub": str(user_id), 
            "exp": expire, 
            "client_type": client_type,
            "iat": datetime.now(timezone.utc),
            "jti": secrets.token_urlsafe(16)    # token unique id
        }
        return jwt.encode(to_encode, self.settings.SECRET_KEY, algorithm='HS256')
    
    async def create_refresh_token(self, user_id: int, client_type: ClientType, device_id: str |None = None) -> str:
        '''create and store refresh token (persistent in db)'''
        # 1. generate random refresh token
        raw_token = secrets.token_urlsafe(32)
        token_hash = pwd_context.hash(raw_token)    # store hash

        # 2. generate refresh token expire time
        expire_at = datetime.now(timezone.utc) + timedelta(days=self.settings.REFRESH_TOKEN_EXPIRE_DAYS)

        # 3. Upsert: the same user with client type and device id, update refresh token(single sign-on)
        result = await self.db.execute(select(UserToken).where(
            UserToken.user_id == user_id,
            UserToken.client_type == client_type,
            UserToken.device_id == device_id,
        ))
        existing = result.scalar_one_or_none()
        if existing:
            existing.refresh_token_hash = token_hash
            existing.expires_at = expire_at
            existing.is_revoked = False
            existing.last_used_at = datetime.now(timezone.utc)
            access_token_jti = existing.access_token_jti
        else:
            access_token_jti = secrets.token_urlsafe(16)
            new_token = UserToken(
                user_id=user_id, 
                client_type=client_type, 
                device_id=device_id,
                refresh_token_hash=token_hash, 
                access_token_jti=access_token_jti, 
                expires_at=expire_at, 
            )
            self.db.add(new_token)
        await self.db.commit()
        return raw_token
    
    # ========= token verification ==========
    async def verify_access_token(self, token: str) -> dict | None:
        '''verify access token (JWT)'''
        try:
            payload = jwt.decode(token, self.settings.SECRET_KEY, algorithms=['HS256'])
            user_id: str = payload.get('sub')
            client_type: str = payload.get('client_type')
            jti: str = payload.get('jti')

            if user_id is None or client_type is None:
                raise JWTError('Invalid access token')
            result = await self.db.execute(select(UserToken).where(
                UserToken.access_token_jti == jti,
                UserToken.is_revoked == True,
            ))
            revoked = result.first()
            if revoked:
                raise JWTError('Access token revoked')
            return {
                'user_id': int(user_id),
                'client_type': client_type,
                'jti': jti
            }
        except ExpiredSignatureError: 
            raise JWTError('Access token expired')
        except JWTError:
            raise JWTError('Invalid access token')

    async def verify_refresh_token(self, client_type: ClientType, refresh_token: str) -> UserToken | None:
        '''verify refresh token(db query and hash compare)'''
        # 1. query all valid refresh tokens of certain client type
        try:
            result = await self.db.execute(select(UserToken).where(
                UserToken.client_type == client_type,
                UserToken.is_revoked == False,
                UserToken.expires_at > datetime.now(timezone.utc),
            ))
            tokens = result.scalars().all()
            # 2. compare refresh token hash
            for token_rec in tokens:
                if pwd_context.verify(refresh_token, token_rec.refresh_token_hash):
                    # 3. update last used time if valid
                    token_rec.last_used_at = datetime.now(timezone.utc)
                    await self.db.commit()
                    return token_rec
        except Exception:
            return None
    
    # ========= token rotation ==========
    async def refresh_with_rotation(self, client_type: ClientType, old_refresh_token: str, device_id: str | None = None) -> tuple[str, str]:
        '''generate new access token and refresh token with refresh token rotation'''
        # 1. verify old refresh token
        token_rec = await self.verify_refresh_token(client_type, old_refresh_token)
        if not token_rec:
            raise ValueError('Invalid refresh token')
        
        user_id = token_rec.user_id

        # 2. revoke old refresh token
        token_rec.is_revoked = True
        await self.db.commit()

        # 3. generate new token pair
        new_access_token = self.create_access_token(user_id, client_type)
        new_refresh_token = await self.create_refresh_token(user_id, client_type, device_id)

        return new_access_token, new_refresh_token
    
    # ========= token revocation ==========
    async def revoke_token(self, user_id: int, client_type: ClientType, device_id: str | None = None, all_devices: bool = False):
        '''revoke refresh token(logout)'''
        stmt = update(UserToken).where(
            UserToken.user_id == user_id,
            UserToken.client_type == client_type,
        )
        if device_id and not all_devices:
            stmt = stmt.where(UserToken.device_id == device_id)

        await self.db.execute(stmt.values(is_revoked=True))
        await self.db.commit()