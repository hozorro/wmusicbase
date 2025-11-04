# -*- encoding: utf-8 -*-
'''
@File      :   config.py
@Time      :   2025/10/18 21:15:39
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   core config
'''


import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import PostgresDsn

class Settings(BaseSettings):
    '''
    settings
    '''
    # ============ 应用配置 ============
    APP_NAME: str = 'WMusicBase'
    DEBUG: bool = False

    HOST: str = '127.0.0.1'
    PORT: int = 8000
    DATABASE_URL: PostgresDsn = 'postgresql+asyncpg://wsonic:kevsN4w*@www.weyeco.com:55432/musictestdb'
    # DATABASE_URL: PostgresDsn = 'sqlite+aiosqlite:///d:\\tmp\\simplify\\musicbase.db'
    MUSIC_LIBRARY_PATH: str = 'H:\\musiclibcorrect'
    MUSIC_FILE_EXTENSIONS: list[str] = ['.mp3', '.flac']
    SECRET_KEY: str = 'dev-secret-key'

    # ============ 基础路径 ============
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
    MEDIA_ROOT: Path = PROJECT_ROOT / 'media'
    TEMP_DIR: Path = MEDIA_ROOT / 'uploads' / 'temp'
    STAGING_DIR: Path = MEDIA_ROOT / 'uploads' / 'staging'
    LOG_DIR: Path = PROJECT_ROOT / 'logs'
    
    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

settings = Settings()
