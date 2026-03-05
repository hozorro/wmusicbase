# -*- encoding: utf-8 -*-
'''
@File      :   token.py
@Time      :   2026/03/02 12:02:42
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   token schemas
'''


from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from enum import Enum

class ClientType(str, Enum):
    PUBLIC = 'player'
    ADMIN = 'admin'
    APP = 'app'
    WEB = 'web'

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'Bearer'
    expires_in: int = 3600

class LoginRequest(BaseModel):
    username: str = Field(..., title='Username')
    password: str = Field(..., title='Password')
    device_id: str | None = Field(None, title='Device ID')

class TokenRefreshRequest(BaseModel):
    refresh_token: str = Field(..., title='Refresh Token')

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = 'bearer'
    expires_in: int = 3600

class UserTokenInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    client_type: str
    device_id: str | None
    expires_at: datetime
    last_used_at: datetime | None
    is_revoked: bool

    
