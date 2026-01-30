# -*- encoding: utf-8 -*-
'''
@File      :   deps.py
@Time      :   2025/10/24 22:43:32
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   deps
'''


from fastapi import Depends, HTTPException, status, Request, WebSocket, WebSocketException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.config import Settings
from app.core.security import verify_token
from app.core.exceptions import credentials_exception
from app.models import User
from cachetools import TTLCache
from app.schemas.user import CurrentUser
from typing import Annotated

_USER_CACHE = TTLCache(maxsize=1000, ttl=900)

auth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/login')

async def get_current_user(
    token: Annotated[str, Depends(auth2_scheme)], 
    db: AsyncSession = Depends(get_db)
) -> CurrentUser:
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
    return CurrentUser(id=user.id, is_admin=user.is_admin, username=user.username)  # if return user, the field not in CurrentUser will not be ignored.?
async def require_login(request: Request, current_user: CurrentUser = Depends(get_current_user)) -> None:
    request.state.user_id = current_user.id
async def require_admin(request: Request, current_user: CurrentUser = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin required')
    request.state.user_id = current_user.id
    return current_user

def get_settings():
    from app.core.config import settings
    return settings

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
LoginDep = Annotated[None, Depends(require_login)]
AdminDep = Annotated[CurrentUser, Depends(require_admin)]

COMMON_DEPS: list = [Depends(get_settings), Depends(get_db), Depends(require_login)]    # use Depends, not SettingsDep...
ADMIN_DEPS: list = [Depends(get_settings), Depends(get_db), Depends(require_admin)]


# deps for websocket
async def get_user_from_token(token: str, db: AsyncSession):
    playload = verify_token(token)
    if not playload:
        return None
    
    username = playload.get('sub')
    if not username:
        return None
    
    result = await db.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()

async def get_websocket_user(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    token = websocket.query_params.get('token')
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason='token required')
    
    user = await get_user_from_token(token, db)
    if not user:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason='invalid token')
    
    return user

async def require_websocket_admin(websocket: WebSocket, user: User = Depends(get_websocket_user)):
    if not user.is_admin:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason='Admin required')
    return user