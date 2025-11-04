# -*- encoding: utf-8 -*-
'''
@File      :   exceptions.py
@Time      :   2025/10/23 17:25:26
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   business exceptions
'''


from fastapi import HTTPException, status

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, 
    detail='Invalid credentials',
    headers={'WWW-Authenticate': 'Bearer'}
)

class BusinessException(HTTPException):
    '''
    业务异常类
    - status_code固定为400
    - business_code为业务错误码（自定义，如1001）
    '''
    def __init__(self, code: int, msg: str, detail: str | None = None):
        super().__init__(status_code=400, detail=msg)
        self.business_code = code
        self.business_msg = msg
        self.detail = detail