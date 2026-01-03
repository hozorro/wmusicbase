# -*- encoding: utf-8 -*-
'''
@File      :   auth.py
@Time      :   2025/10/24 22:27:20
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   authentication router
'''


from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.db import get_db
from app.core.security import verify_password, create_access_token, get_password_hash, create_refresh_token, verify_token
from app.core.exceptions import credentials_exception
from app.core.deps import auth2_scheme, get_current_user
from app.core.state import system_state
from app.models import User
from app.schemas.common import ResponseModel
from app.schemas.sysinfo import InitializedResponse
from app.schemas.user import UserCreate, UserResponse, TokenData
from typing import Annotated

router = APIRouter()

@router.post('/login', response_model=ResponseModel[TokenData])
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db),
):
    ''' login'''
    
    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form_data.password, user.password_hash):
        raise credentials_exception
    
    access_token = create_access_token(data={'sub': user.username})
    refresh_token = create_refresh_token(data={'sub': user.username})
    user.refresh_token = refresh_token
    await db.commit()

    return ResponseModel(
        code=200,
        msg='ok',
        data=TokenData(
            access_token=access_token, 
            refresh_token=refresh_token,
            token_type='bearer'
        )
    )

@router.post('/register', response_model=ResponseModel[UserResponse])
async def register(
    user: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    # check if any user exists(can only register when first run and no user exists)
    user_count = await db.scalar(select(func.count(User.id)))
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Registration closed after first user'
        )
    # create user
    hash_password = get_password_hash(user.password)
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

@router.get('/refresh', response_model=ResponseModel[TokenData])
async def refresh_token(
    refresh_token: Annotated[str, Depends(auth2_scheme)],
    db: AsyncSession = Depends(get_db)
):
    ''' refresh token'''
    payload = verify_token(refresh_token)
    if not payload or payload.get('type') != 'refresh':
        raise credentials_exception
    username = payload.get('sub')
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or user.refresh_token != refresh_token:
        raise credentials_exception
    new_access_token = create_access_token(data={'sub': username})
    return ResponseModel(
        code=200,
        msg='ok',
        data=TokenData(access_token=new_access_token, token_type='bearer')
    )

@router.post('/logout', response_model=ResponseModel[None])
async def logout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ResponseModel:
    ''' logout'''
    current_user.refresh_token = None
    await db.commit()
    return ResponseModel(code=200, msg='ok', data=None)

@router.get('/me', response_model=ResponseModel[UserResponse])
async def get_current_user(
    current_user: User = Depends(get_current_user)
):
    ''' get current user'''
    return ResponseModel(
        code=200,
        msg='ok',
        data=UserResponse.model_validate(current_user)
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