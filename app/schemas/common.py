# -*- encoding: utf-8 -*-
'''
@File      :   common.py
@Time      :   2025/10/23 17:42:05
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   common response struct
'''


from pydantic import BaseModel
from typing import TypeVar, Generic

DataT = TypeVar('DataT', bound=BaseModel)

class ResponseModel(BaseModel, Generic[DataT]):
    '''统一成功响应结构'''
    code: int = 200
    msg: str = 'ok'
    data: DataT | None = None

    class Config:
        # 允许字段为None且不被过滤
        from_attributes = True

class ErrorResponseModel(BaseModel):
    '''统一错误响应结构（仅用于文档，实际由异常处理器返回）'''
    code: int
    msg: str = 'error'
    detail: str | None = None