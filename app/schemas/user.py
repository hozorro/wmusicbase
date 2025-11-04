# -*- encoding: utf-8 -*-
'''
@File      :   user.py
@Time      :   2025/10/29 12:47:26
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   user schema
'''


from pydantic import BaseModel, ConfigDict
from datetime import datetime

class UserBase(BaseModel):
    username: str
    is_admin: bool = False

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    last_login_at: datetime | None

class TokenData(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str
