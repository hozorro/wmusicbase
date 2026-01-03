# -*- encoding: utf-8 -*-
'''
@File      :   system.py
@Time      :   2025/10/26 17:38:28
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   admin system router
'''


from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.db import get_db
from app.models import User
from app.schemas.common import ResponseModel
from app.schemas.sysinfo import InitializedResponse

router = APIRouter()

@router.get('/initialized', response_model=ResponseModel[InitializedResponse])
async def check_system_initialized(db: AsyncSession = Depends(get_db)):
    '''check whether system has been initialized, if any user exists, system is initialized'''
    result = await db.execute(select(User).limit(1))
    has_user = result.scalar_one_or_none() is not None
    return ResponseModel(code=200, msg='ok', data=InitializedResponse(initialized=has_user))