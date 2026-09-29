# -*- encoding: utf-8 -*-
'''
@File      :   steam.py
@Time      :   2025/12/23 11:15:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   stream router, for audio streaming, token is attached to url, not header
'''


import os
import urllib
from itsdangerous import BadSignature, SignatureExpired
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import Response
from app.services.file_service import StreamService
from app.core.exceptions import BusinessException
from app.utils.streaming import signer, parse_range

router = APIRouter()

@router.get('/{track_id}', response_class=Response)
async def stream_track(track_id: int, token: str, request: Request, service: StreamService = Depends(StreamService)):
    try:
        raw = signer.unsign(token, max_age=600).decode()
    except SignatureExpired:
        raise BusinessException(
            code=30301, 
            msg='token expired when streaming track', 
            status_code=status.HTTP_403_FORBIDDEN
        )
    except BadSignature:
        raise BusinessException(
            code=30302, 
            msg='invalid token when streaming track', 
            status_code=status.HTTP_403_FORBIDDEN
        )
    
    signed_tid, user_id = raw.split(':')
    await service.check_user(int(user_id))
    signed_tid = int(signed_tid)

    if signed_tid != track_id:
        raise BusinessException(
            code=30303, 
            msg='token mismatch when streaming track', 
            status_code=status.HTTP_403_FORBIDDEN
        )
    
    track_path = await service.get_track_path(track_id)
    if not track_path:
        raise BusinessException(
            code=30304, 
            msg='track file not found', 
            status_code=status.HTTP_404_NOT_FOUND
        )
    
    inner = '/lib/' + urllib.parse.quote(track_path)
    filename = os.path.basename(track_path)

    return Response(
        status_code=200,
        headers={
            'X-Accel-Redirect': inner,
            'Content-Disposition': f"inline; filename*=utf-8''{urllib.parse.quote(filename)}",
            'Accept-Ranges': 'bytes',
        }
    )
    # file_size = os.path.getsize(track_file)
    # mime_type, _ = mimetypes.guess_type(track_file)
    # mime_type = mime_type or 'audio/mpeg'

    # range_header = request.headers.get('Range')

    # range request from safari / chrome
    # if range_header:
    #     start, end = parse_range(range_header, file_size)
    #     chunk_size = end - start + 1

    #     with open(track_file, 'rb') as f:
    #         f.seek(start)
    #         data = f.read(chunk_size)

    #     headers = {
    #         'Content-Range': f'bytes {start}-{end}/{file_size}',
    #         'Content-Length': str(chunk_size),
    #         'Accept-Ranges': 'bytes',
    #         'Content-Type': mime_type
    #     }

    #     return Response(data, status_code=206, headers=headers)
    
    # request without range(first load)
    # with open(track_file, 'rb') as f:
    #     data = f.read()
    # headers = {
    #     'Content-Length': str(file_size),
    #     'Accept-Ranges': 'bytes',
    #     'Content-Type': mime_type
    # }
    # return Response(data, status_code=200, headers=headers)