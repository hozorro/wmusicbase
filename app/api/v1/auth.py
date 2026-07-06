# -*- encoding: utf-8 -*-
'''
@File      :   auth.py
@Time      :   2025/10/24 22:27:20
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   authentication router
'''


from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select, func
from app.core.exceptions import credentials_exception
from app.core.deps import get_current_user, ClientTypeDep, SettingsDep, DbDep
from app.core.state import system_state
from app.models.user import User
from app.schemas.common import ResponseModel
from app.schemas.sysinfo import InitializedResponse
from app.schemas.user import UserCreate, UserResponse, CurrentUser
from app.schemas.token import LoginRequest, TokenRefreshRequest, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter()

@router.post('/login', response_model=ResponseModel[TokenResponse])
async def login(
    data: LoginRequest,
    client_type: ClientTypeDep,
    service: AuthService = Depends(AuthService),
):
    ''' login'''
    user = await service.authenticate_user(data.username, data.password)
    if not user:
        raise credentials_exception
    
    access_token = service.create_access_token(user.id, client_type)
    refresh_token = await service.create_refresh_token(user.id, client_type, data.device_id)

    return ResponseModel(
        code=200,
        msg='ok',
        data=TokenResponse(
            access_token=access_token, 
            refresh_token=refresh_token
        )
    )

@router.post('/register', response_model=ResponseModel[UserResponse])
async def register(
    user: UserCreate,
    db: DbDep,
    service: AuthService = Depends(AuthService)
):
    # check if any user exists(can only register when first run and no user exists)
    user_count = await db.scalar(select(func.count(User.id)))
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Registration closed after first user'
        )
    # create user
    hash_password = service.get_password_hash(user.password)
    is_admin = user.is_admin
    user_db = User(
        username=user.username,
        password_hash=hash_password,
        is_admin=is_admin
    )
    db.add(user_db)
    await db.commit()

    return ResponseModel(
        code=200,
        msg='ok',
        data=UserResponse.model_validate(user_db)
    )

@router.post('/refresh', response_model=ResponseModel[TokenResponse])
async def refresh_token(
    data: TokenRefreshRequest,
    request: Request,
    client_type: ClientTypeDep,
    settings: SettingsDep,
    service: AuthService = Depends(AuthService)
):
    ''' refresh token'''
    try:
        new_access, new_refresh = await service.refresh_with_rotation(
            client_type,
            data.refresh_token,
            device_id=request.headers.get('X-Device-Id')
        )
        return ResponseModel(
            code=200,
            msg='ok',
            data=TokenResponse(
                access_token=new_access, 
                refresh_token=new_refresh,
                expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
            )
        )
    except Exception as e:
        raise credentials_exception

@router.post('/logout', response_model=ResponseModel[None])
async def logout(
    request: Request,
    client_type: ClientTypeDep,
    service: AuthService = Depends(AuthService),
    current_user: User = Depends(get_current_user),
) -> ResponseModel:
    ''' logout'''
    logout_all = request.query_params.get('all', 'false') == 'true'
    device_id = request.headers.get('X-Device-Id')
    await service.revoke_token(current_user.id, client_type, device_id, logout_all)
    return ResponseModel(code=200, msg='ok', data=None)

@router.get('/me', response_model=ResponseModel[CurrentUser])
async def get_me(
    current_user: User = Depends(get_current_user)
):
    ''' get current user'''
    return ResponseModel(
        code=200,
        msg='ok',
        data=CurrentUser.model_validate(current_user)
    )

@router.get('/test', response_model=ResponseModel[InitializedResponse])
async def test():
    ''' test'''
    if not system_state.is_scanning:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Scanning is not running'
        )
    return ResponseModel(
        code=200,
        msg='ok',
        data={'initialized': system_state.is_scanning}
    )