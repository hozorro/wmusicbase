# -*- encoding: utf-8 -*-
'''
@File      :   deps.py
@Time      :   2025/10/24 22:43:32
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   deps
'''


from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.security import verify_token
from app.core.exceptions import credentials_exception
from app.models import User
from cachetools import TTLCache
from typing import Annotated

_USER_CACHE = TTLCache(maxsize=1000, ttl=900)

auth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/login')

async def get_current_user(
    token: Annotated[str, Depends(auth2_scheme)], 
    db: AsyncSession = Depends(get_db)
):
    playload = verify_token(token)
    if not playload:
        raise credentials_exception
    
    username = playload.get('sub')
    if not username:
        raise credentials_exception
    if username in _USER_CACHE:
        return _USER_CACHE[username]
    
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise credentials_exception
    _USER_CACHE[username] = user
    return user

async def require_admin(current_user: User = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin required')
    return current_user