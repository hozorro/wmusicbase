# -*- encoding: utf-8 -*-
'''
@File      :   signer.py
@Time      :   2025/12/23 11:25:33
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   create signed url, parse range for safari browser
'''


from fastapi import HTTPException
from itsdangerous import TimestampSigner
from app.core.config import settings

signer = TimestampSigner(settings.SECRET_KEY)

def parse_range(range_header: str, file_size: int):
    """
    Safari will send Range: bytes... request,
    But StreamingResponse doesn't support it.
    So we need to parse it and return the start and end position.
    :param range_header: str, range header from request
    :param file_size: int, file size
    """
    try:
        _, range_spec = range_header.split('=')
        start_str, end_str = range_spec.split('-')

        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1

        if start > end or end >= file_size:
            raise ValueError('Range out of bounds')
        
        return start, end
    except Exception as e:
        raise HTTPException(status_code=416, detail='Invalid range header')