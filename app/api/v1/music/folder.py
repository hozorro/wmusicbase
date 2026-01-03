# -*- encoding: utf-8 -*-
'''
@File      :   folders.py
@Time      :   2025/10/20 14:07:53
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router folder
'''


from fastapi import APIRouter, Depends
from app.core.deps import COMMON_DEPS
from app.schemas.common import ResponseModel
from app.schemas.folder import FolderResponse
from app.services.folder_service import FolderService

router = APIRouter(dependencies=COMMON_DEPS)

@router.get('/{folder_id}', response_model=ResponseModel[FolderResponse])
async def get_folder(folder_id: int, service: FolderService = Depends(FolderService)):
    folder = await service.get_folder(folder_id)
    return ResponseModel(data=FolderResponse.model_validate(folder))