# -*- encoding: utf-8 -*-
'''
@File      :   security.py
@Desc      :   security helpers (compatibility layer)
'''

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# 本模块原有的 create_access_token / create_refresh_token / verify_token 是一套
# 无人 import 的重复 JWT 实现（默认 10 分钟 / 7 天），与真实配置
# app/core/config.py 的 ACCESS_TOKEN_EXPIRE_MINUTES(7d) / REFRESH_TOKEN_EXPIRE_DAYS(30d)
# 相矛盾，已移除，避免误导后续维护。
# JWT 生成与校验的唯一真源：app/services/auth_service.py::AuthService
