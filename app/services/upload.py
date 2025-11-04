# -*- encoding: utf-8 -*-
'''
@File      :   upload.py
@Time      :   2025/10/22 21:40:29
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   upload service
'''


import uuid
import shutil
import re
import aiofiles
from pathlib import Path
from app.core.config import settings
from logging import getLogger

logger = getLogger(__name__)

def sanitize_filename(filename: str) -> str:
    '''去除文件名中的非法字符'''
    return re.sub(r'[\\/:*?"<>|]', '_', filename)

async def save_temp_file(file_data: bytes, filename: str) -> Path:
    '''保存临时文件到temp目录，返回路径'''
    safe_name = sanitize_filename(filename)
    temp_path = settings.TEMP_DIR / f'{uuid.uuid4().hex}_{safe_name}'
    async with aiofiles.open(temp_path, 'wb') as f:
        await f.write(file_data)
    return temp_path

def create_staging_session() -> str:
    '''创建整理会话， 返回session_id'''
    session_id = str(uuid.uuid4())
    session_dir = settings.STAGING_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / 'songs').mkdir(parents=True, exist_ok=True)
    (session_dir / 'artist_images').mkdir(parents=True, exist_ok=True)
    return session_id

def move_single_to_staging(session_id: str, temp_file_id: str) -> str:
    '''将temp中的单个文件移入staging会话'''
    temp_path = settings.TEMP_DIR / temp_file_id
    if not temp_path.exists(): 
        raise FileNotFoundError(f'Temp file {temp_file_id} not found')
    session_dir = settings.STAGING_DIR / session_id
    dest = session_dir / 'songs' / temp_file_id
    shutil.move(str(temp_path), str(dest))
    return dest

def move_all_to_staging(session_id: str) -> list[str]:
    '''将temp中的所有文件移入staging会话'''
    session_songs_dir = settings.STAGING_DIR / session_id / 'songs'
    move_files = []

    if not settings.TEMP_DIR.exists():
        return move_files
    for temp_file in settings.TEMP_DIR.iterdir():
        if temp_file.isfile():
            dest = session_songs_dir / temp_file.name
            try:
                shutil.move(str(temp_file), str(dest))
                move_files.append(temp_file.name)
            except Exception as e:
                logger.error(f'Failed to move {temp_file} to {dest}: {e}')
    return move_files
