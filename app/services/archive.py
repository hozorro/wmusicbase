# -*- encoding: utf-8 -*-
'''
@File      :   archive.py
@Time      :   2025/10/22 21:51:24
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   archive staged files
'''


import shutil
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.utils.metadata import extract_metadata
from app.utils.pinyin import get_artist_sort_fields
from app.services.processor import MusicFileProcessor

def is_chinese(text: str) -> bool:
    '''判断字符串是否包含中文'''
    return any('\u4e00' <= char <= '\u9fff' for char in text)

def get_initial_group(initial: str) -> str:
    '''获取首字母分组标识'''
    if initial == '_':
        return 'Z_'
    elif 'A' <= initial <= 'G':
        return 'A-G'
    elif 'H' <= initial <= 'N':
        return 'H-N'
    elif 'O' <= initial <= 'T':
        return 'O-T'
    else:
        return 'U-Z'
    
def generate_target_path(astist_name: str, album_title: str | None, track_title: str) -> Path:
    '''生成归档目标路径'''
    lang = 'Chinese' if is_chinese(astist_name) else 'Foreign'
    _, initial = get_artist_sort_fields(astist_name)
    group = get_initial_group(initial)

    base = Path(settings.MUSIC_LIBRARY_PATH) / lang / group / astist_name
    if album_title:
        return base / album_title / track_title
    else:
        return base / track_title
    
async def archive_session(session_id: str, db: AsyncSession) -> list[str]:
    '''将 staging 会话中的文件归档到音乐库'''
    session_dir = settings.STAGING_DIR / session_id
    songs_dir = session_dir / 'songs'
    errors = []

    for song_file in songs_dir.iterdir():
        if song_file.suffix.lower() not in settings.MUSIC_FILE_EXTENSIONS:
            continue

        # 1. 提取元数据（用于路径生成）
        meta = extract_metadata(song_file)
        if not meta:
            errors.append(f'Failed to extract metadata from {song_file}')
            continue

        # 2. 确定artist_name（用于路径生成）
        artist_name = 'Unknown Artist'
        if meta['artists']:
            artist_name = meta['artists'][0]
        elif meta.get('albumartist'):
            artist_name = meta['albumartist'][0]

        # 3. 确定文件名（优先track_title，然后是filename）
        filename = meta.get('title') or song_file.name

        # 4. 生成目标路径
        target_path = generate_target_path(artist_name, meta.get('album'), filename)
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 5. 移动文件
        try:
            shutil.move(str(song_file), str(target_path))
        except Exception as e:
            errors.append(f'Failed to move {song_file} to {target_path}: {e}')
            continue

        # 6. 触发扫描（入库）
        try:
            processor = MusicFileProcessor(db)
            await processor.process_single_file(target_path, Path(settings.MUSIC_LIBRARY_PATH))
            await db.commit()
        except Exception as e:
            await db.rollback()
            errors.append(f'Failed to process {target_path}: {e}')
    
    # 7. 删除staging会话
    shutil.rmtree(str(session_dir))
    return errors
