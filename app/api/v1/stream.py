# -*- encoding: utf-8 -*-
'''
@File      :   steam.py
@Time      :   2025/12/23 11:15:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   stream router, for audio streaming, token is attached to url, not header
'''


from itsdangerous import BadSignature, SignatureExpired
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from app.services.file_service import StreamService
from app.utils.signer import signer

router = APIRouter()

@router.get('/{track_id}', response_class=StreamingResponse)
async def stream_track(track_id: int, token: str, service: StreamService = Depends(StreamService)):
    try:
        raw = signer.unsign(token, max_age=600).decode()
    except SignatureExpired:
        raise HTTPException(status_code=401, detail='Token expired')
    except BadSignature:
        raise HTTPException(status_code=401, detail='Invalid token')
    
    signed_tid, user_id = raw.split(':')
    await service.check_user(int(user_id))
    signed_tid = int(signed_tid)

    if signed_tid != track_id:
        raise HTTPException(status_code=401, detail='Token mismatch')
    
    track_file = await service.get_audio_file(track_id)
    if not track_file:
        raise HTTPException(status_code=404, detail='Track not found')
    
    def iter_file():
        with open(track_file, 'rb') as f:
            while chunk := f.read(1024 * 1024):
                yield chunk

    return StreamingResponse(iter_file(), media_type='audio/mpeg')