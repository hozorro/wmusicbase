# -*- encoding: utf-8 -*-
'''
@File      :   deps.py
@Time      :   2025/10/24 22:43:32
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   deps
'''


from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.core.config import Settings
from app.core.exceptions import credentials_exception
from app.schemas.token import ClientType
from typing import Annotated

# ========== client type ==========
async def get_client_type(request: Request) -> ClientType:
    '''
    determine client type based on request headers or url path.
    priority: headers > url path > default.
    '''
    client_header = request.headers.get('X-Client-Type')
    if client_header:
        try:
            return ClientType(client_header)
        except ValueError:
            pass

    path = request.url.path
    if '/admin/' in path or path.startswith('/api/v1/admin'):
        return ClientType.ADMIN
    elif path.startswith('/api/v1/music'):
        return ClientType.PUBLIC
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, 
        detail='Invalid client type, Please set X-Client-Type header.'
    )

def get_settings():
    from app.core.config import settings
    return settings

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
ClientTypeDep = Annotated[ClientType, Depends(get_client_type)]


from fastapi.security import OAuth2PasswordBearer
from app.services.auth_service import AuthService
from app.schemas.user import CurrentUser
from app.models import User
from cachetools import TTLCache

_USER_CACHE = TTLCache(maxsize=1000, ttl=900)

auth2_scheme = OAuth2PasswordBearer(tokenUrl='auth/login', auto_error=False)

async def get_current_user(
    token: Annotated[str, Depends(auth2_scheme)], 
    db: AsyncSession = Depends(get_db),
    client_type: ClientType = Depends(get_client_type),
    service: AuthService = Depends(AuthService)
) -> CurrentUser:
    if not token:
        return credentials_exception
    
    try:
        payload = await service.verify_access_token(token)
        if payload['client_type'] != client_type:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Token type ({payload["client_type"]}) mismatch with endpoint ({client_type})'
            )

        user_id = payload.get('user_id')
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f'Token type ({payload["user_id"]}) mismatch)'
            )
        if user_id in _USER_CACHE:
            return _USER_CACHE[user_id]
        
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise credentials_exception
        _USER_CACHE[user_id] = user
        return CurrentUser(id=user.id, is_admin=user.is_admin, username=user.username)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f'Failed to verify token: {str(e)}'
        )
async def require_login(request: Request, current_user: CurrentUser = Depends(get_current_user)) -> None:
    request.state.user_id = current_user.id
async def require_admin(request: Request, current_user: CurrentUser = Depends(get_current_user), client_type: ClientType = Depends(get_client_type)):
    if not current_user.is_admin or client_type != ClientType.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Admin required')
    request.state.user_id = current_user.id
    return current_user


LoginDep = Annotated[None, Depends(require_login)]
AdminDep = Annotated[CurrentUser, Depends(require_admin)]

COMMON_DEPS: list = [Depends(get_settings), Depends(get_db), Depends(require_login)]    # use Depends, not SettingsDep...
ADMIN_DEPS: list = [Depends(get_settings), Depends(get_db), Depends(require_admin)]
