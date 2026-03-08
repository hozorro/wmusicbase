# -*- encoding: utf-8 -*-
'''
@File      :   config.py
@Time      :   2025/10/18 21:15:39
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   core config
'''


from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, field_validator, ValidationInfo
from typing import Optional, Any

# ==============base path constant, project root directory =================
PROJECT_BASE = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    '''settings'''
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore',
    )
    # ============ app config =============
    APP_NAME: str = Field('WMusicBase', description='app name')
    DEBUG: bool = Field(False, description='is debug mode(MUST be turned off in production)')

    # ============ server config ==========
    HOST: str = '127.0.0.1'
    PORT: int = 8000

    # =========== database config ===========
    # PostgreSQL database URL（can be joined by vars, or set url directly）
    DB_USER: str = Field(..., description='database username')
    DB_PASSWORD: str = Field(..., description='database password')
    DB_HOST: str = Field('localhost', description='database host')
    DB_PORT: int = Field(5432, description='database port')
    DB_NAME: str = Field(..., description='database name')
    DATABASE_URL: Optional[PostgresDsn] = Field(None, description='database connection URL')
    
    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def assemble_db_url(cls, v: Optional[str], info: ValidationInfo) -> Any:
        if v is not None and  isinstance(v, (str, PostgresDsn)):
            return v
        
        data = info.data
        required_fields = ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_NAME']
        for field in required_fields:
            if field not in data or data[field] is None:
                raise ValueError(f'Database configuration error: {field} is required')
        return PostgresDsn.build(
            scheme='postgresql+asyncpg',
            username=data['DB_USER'],
            password=data['DB_PASSWORD'],
            host=data['DB_HOST'],
            port=data['DB_PORT'],
            path=data['DB_NAME']
        )
    
    # DATABASE_URL: PostgresDsn = 'sqlite+aiosqlite:///d:\\tmp\\simplify\\musicbase.db'

    # ======= ==== Security config =============
    SECRET_KEY: str = Field(..., description='JWT key(MUST randomly generated in production)')
    ACOUSTID_API_KEY: str = Field(..., description='AcoustID dev api-key(from acoustid.org)')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60 * 24 * 7, description='access token expire minutes(default: 7 days)')
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(30, description='refresh token expire days(default: 30)')

    # =========== Music library config =========
    MUSIC_LIBRARY_PATH: Path = Field(default=PROJECT_BASE / 'music_library', description='Music library root directory(can be overridden by environment variables)')
    MUSIC_FILE_EXTENSIONS: list[str] = Field(['.mp3', '.flac'], description='Music file extensions(default: [.mp3, .flac]，can be overridden by environment variables)')

    # ========== App base path config ===========
    PROJECT_ROOT: Path = Field(default=PROJECT_BASE, description='Project root directory(can be overridden by environment variables)')
    MEDIA_ROOT: Path = Field(default=PROJECT_BASE / 'media', description='Media file root directory(can be overridden by environment variables)') 
    LOG_DIR: Path = Field(default=PROJECT_BASE / 'logs', description='Log directory(can be overridden by environment variables)') 
    
    # media file directory, can not be changed by config file, only as property
    @property
    def TEMP_DIR(self) -> Path:
        '''upload temp file dir'''
        return self.MEDIA_ROOT / 'uploads' / 'temp'
    @property
    def STAGING_DIR(self) -> Path:
        '''stage session dir'''
        return self.MEDIA_ROOT / 'uploads' / 'staging'
    @property
    def PLAYLISTS_TMP_DIR(self) -> Path:
        '''playlist temp file dir'''
        return self.MEDIA_ROOT / 'playlists' / 'tmp'
    
    # artwork dir
    @property
    def ARTWORK_DIR(self) -> Path:
        '''artwork root dir'''
        return self.MEDIA_ROOT / 'artwork'
    @property
    def TRACK_ARTWORK_DIR(self) -> Path:
        '''track artwork dir'''
        return self.ARTWORK_DIR / 'tracks'
    @property
    def ALBUM_ARTWORK_DIR(self) -> Path:
        '''album artwork dir'''
        return self.ARTWORK_DIR / 'albums'
    @property
    def ARTIST_ARTWORK_DIR(self) -> Path:
        '''artist artwork dir'''
        return self.ARTWORK_DIR / 'artists'
    @property
    def PLAYLIST_ARTWORK_DIR(self) -> Path:
        '''playlist artwork dir'''
        return self.ARTWORK_DIR / 'playlists'
    
    @property
    def TMP_ARTWORK_DIR(self) -> Path:
        '''tmp artwork dir'''
        return self.ARTWORK_DIR / 'tmp'
    
    @field_validator('MEDIA_ROOT', 'LOG_DIR', mode='before')
    @classmethod
    def convert_str_to_path(cls, v: Path | str) -> Path | None:
        """
        convert str to Path
        """
        if isinstance(v, str):
            v = v.replace('\\', '/')
            path = Path(v)
        elif isinstance(v, Path):
            path = v
        else: 
            raise ValueError(f'Invalid path: {v}')

        return path
    
    # ========== CORS config ============
    CORS_ORIGINS: list[str] = Field(['*'], description='allowed origins')

    # ========== CoverArt API config ====
    COVER_ART_BASE_URL: str = Field('http://coverartarchive.org', description='cover art base url')
    COVER_ART_PATH: list[str] = Field([
        '/release/{release_id}/front',
        '/release/{release_id}/back',
    ], description='cover art path')
    CACHE_EXPIRE: int = Field(300, description='cache expire time(seconds)')
    CACHE_MAX: int = Field(100, description='cache max items')

    # ========== Lyric config ===========
    LYRIC_OUT_BASE_URL:str = Field('http://localhost:28883/api/v1/lyrics/', description='lyric server address base url')

    # ========== Other variables ========
    MAX_UPDATE_META_BATCH_COUNT: int = Field(20, description='max batch count of items to update metadata')
    
settings = Settings()

def create_required_directories():
    dirs_to_create = [
        settings.MEDIA_ROOT,
        settings.LOG_DIR,
        settings.TEMP_DIR,
        settings.STAGING_DIR,
        settings.PLAYLISTS_TMP_DIR,
        settings.TRACK_ARTWORK_DIR,
        settings.ALBUM_ARTWORK_DIR,
        settings.ARTIST_ARTWORK_DIR,
        settings.PLAYLIST_ARTWORK_DIR,
        settings.TMP_ARTWORK_DIR
    ]
    for dir_path in dirs_to_create:
        abs_path = dir_path.resolve()
        abs_path.mkdir(parents=True, exist_ok=True)