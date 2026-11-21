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

# user_tokens.device_id 是 NOT NULL：客户端未上报时统一使用此值，
# 避免插入 NULL 触发 IntegrityError 并被误判为凭证失效
DEFAULT_DEVICE_ID = 'unknown-device'


class AuthService:
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    # ========= password management =============
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        return pwd_context.hash(password)
    
    # ========= authentication =========
    async def authenticate_user(self, username: str, password: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user or not self.verify_password(password, user.password_hash):
            return None
        return user
    
    # ========= token generation ==========
    def create_access_token(self, user_id: int, client_type: str, expires_delta: timedelta | None = None, jti: str | None = None) -> str:
        '''create access token (JWT)

        jti 必须传入设备行的 access_token_jti，否则 logout 的撤销检查无法命中该 token。
        未传入时随机生成（仅用于测试/无设备上下文的场景）。
        '''
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode = {
            "sub": str(user_id), 
            "exp": expire, 
            "client_type": client_type,
            "iat": datetime.now(timezone.utc),
            "jti": jti or secrets.token_urlsafe(16)    # 与 UserToken.access_token_jti 关联
        }
        return jwt.encode(to_encode, self.settings.SECRET_KEY, algorithm='HS256')
    
    async def create_refresh_token(self, user_id: int, client_type: ClientType, device_id: str | None = None) -> str:
        '''create and store refresh token (persistent in db)'''
        device_id = device_id or DEFAULT_DEVICE_ID
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

    async def get_device_token_jti(self, user_id: int, client_type: ClientType, device_id: str | None = None) -> str | None:
        '''取设备行上的 access_token_jti，供签发 access token 时关联'''
        result = await self.db.execute(select(UserToken.access_token_jti).where(
            UserToken.user_id == user_id,
            UserToken.client_type == client_type,
            UserToken.device_id == (device_id or DEFAULT_DEVICE_ID),
        ))
        return result.scalar_one_or_none()
    
    # ========= token verification ==========
    async def verify_access_token(self, token: str) -> dict | None:
        '''verify access token (JWT)'''
        try:
            payload = jwt.decode(token, self.settings.SECRET_KEY, algorithms=['HS256'])
            user_id = payload.get('sub', None)
            client_type = payload.get('client_type', None)
            jti: str = payload.get('jti', '')

            if user_id is None or client_type is None:
                raise JWTError('Invalid access token')
            # 签发的 token 现在携带设备行的 access_token_jti；
            # logout 把该行置 is_revoked=True 后，这里就能命中并拒绝旧 access token
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
        '''verify refresh token(db query and hash compare)

        DB / 缓存等临时故障直接向外抛出，由端点分流为 503，
        绝不吞成 None 再伪装成「凭证失效」。
        '''
        result = await self.db.execute(select(UserToken).where(
            UserToken.client_type == client_type,
            UserToken.is_revoked == False,
            UserToken.expires_at > datetime.now(timezone.utc),
        ))
        for token_rec in result.scalars().all():
            try:
                matched = pwd_context.verify(refresh_token, token_rec.refresh_token_hash)
            except (ValueError, TypeError):
                continue  # 损坏的历史记录不参与匹配
            if matched:
                token_rec.last_used_at = datetime.now(timezone.utc)
                await self.db.commit()
                return token_rec
        return None
    
    # ========= token refresh ==========
    async def refresh_session(self, client_type: ClientType, refresh_token: str, device_id: str | None = None) -> tuple[str, str]:
        '''签发新的 access token；refresh token 保持原值（方案A：不做一次性轮换）

        离线优先的 PWA 会在网络抖动时重放同一 refresh token。若每次刷新都轮换，
        「后端已撤销旧 token 但响应丢失」会让客户端永久持有一个作废凭证，
        反复刷新 -> 反复 401 -> 反复跳登录页。refresh token 仍是入库哈希、
        30 天有效、logout 可撤销，安全性由这些约束保证。
        device_id 仅为兼容旧调用保留，不再参与刷新逻辑。
        '''
        token_rec = await self.verify_refresh_token(client_type, refresh_token)
        if not token_rec:
            raise ValueError('Invalid refresh token')

        new_access_token = self.create_access_token(
            token_rec.user_id,
            client_type,
            jti=token_rec.access_token_jti or None,
        )
        return new_access_token, refresh_token
    
    # ========= token revocation ==========
    async def revoke_token(self, user_id: int, client_type: ClientType, device_id: str | None = None, all_devices: bool = False):
        '''revoke refresh token(logout)'''
        stmt = update(UserToken).where(
            UserToken.user_id == user_id,
            UserToken.client_type == client_type,
        )
        if not all_devices:
            # 不带设备头时只撤销默认设备，不能连带踢掉该用户所有设备
            stmt = stmt.where(UserToken.device_id == (device_id or DEFAULT_DEVICE_ID))

        await self.db.execute(stmt.values(is_revoked=True))
        await self.db.commit()
