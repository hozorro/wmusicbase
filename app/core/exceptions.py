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
    business exception class
    - status_code is fixed as 400
    - business_code is customized for business exception
    '''

    '''Customized business exception code
    10203: partial success
    10404: resource not found
    10405: resource already exists
    10406: resource not allowed
    10500: operation failed
    to be continued
    '''
    def __init__(self, code: int, msg: str, detail: str | None = None):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
        self.business_code = code
        self.business_msg = msg
        self.detail = detail