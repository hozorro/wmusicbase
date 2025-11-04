# -*- encoding: utf-8 -*-
'''
@File      :   upload.py
@Time      :   2025/10/25 11:32:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   upload, stagging and archive router
'''


from fastapi import APIRouter, UploadFile, HTTPException, Form, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.upload import save_temp_file, create_staging_session, move_all_to_staging, move_single_to_staging
from app.services.archive import archive_session
from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import BusinessException
from app.schemas.common import ResponseModel
from typing import Annotated

router = APIRouter()

settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
settings.STAGING_DIR.mkdir(parents=True, exist_ok=True)

@router.post('/uploadfile')
async def upload_file(file: UploadFile, name: Annotated[str | None, Form()] = None):
    if file.content_type not in ['audio/mpeg', 'audio/flac']:
        raise HTTPException(status_code=400, detail='Only mp3 and flac files are allowed')
    content = await file.read()
    if name:
        filename = name
    else:
        filename = file.filename
    _ = await save_temp_file(content, filename)
    await file.close()
    return ResponseModel(code=200, msg='ok', data=filename)

@router.post('/staging/sessions')
async def create_session():
    session_id = create_staging_session()
    return ResponseModel(code=200, msg='ok', data=session_id)

@router.get('/staging/sessions')
async def list_staging_sessions():
    '''列出所有未归档整理的会话'''
    if not settings.STAGING_DIR.exists():
        return ResponseModel(code=200, msg='ok', data=[])
    
    sessions = []
    for item in settings.STAGING_DIR.iterdir():
        if item.is_dir():
            songs_dir = item / 'songs'
            song_count = len(list(songs_dir.iterdir())) if songs_dir.exists() else 0

            mtime = item.stat().st_mtime

            sessions.append({
                'session_id': item.name,
                'song_count': song_count,
                'created_at': mtime
            })
    sessions.sort(key=lambda x: x['created_at'], reverse=True)
    return ResponseModel(code=200, msg='ok', data=sessions)

@router.post('/staging/sessions/{session_id}/files')
async def add_file_to_session(
    session_id: str, 
    temp_file_id: Annotated[
        str | None, 
        Query(description='Optional: specific temp file ID. If not provided, will move all files in temp to staging.')
    ] = None
):
    
    session_dir = settings.STAGING_DIR / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail='Session not found')
    
    try:
        if temp_file_id is None:
            # 批量移动所有temp文件
            moved = move_all_to_staging(session_id)
            return ResponseModel(code=200, msg='ok', data={'moved_files': moved, 'count': len(moved)})
        else:
            # 移动单个temp文件
            moved_file = move_single_to_staging(session_id, temp_file_id)
            return ResponseModel(code=200, msg='ok', data=moved_file)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post('/staging/sessions/{session_id}/archive')
async def archive_session_route(session_id: str, db: AsyncSession = Depends(get_db)):
    errors = await archive_session(session_id, db)
    if errors:
        raise BusinessException(code=1002, msg='partial success', detail='\n'.join(errors))
    return ResponseModel(code=200, msg='ok', data='archived')