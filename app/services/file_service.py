# -*- encoding: utf-8 -*-
'''
@File      :   archive.py
@Time      :   2025/10/22 21:51:24
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   archive staged files
'''


import shutil, json, re, uuid, aiofiles
from datetime import datetime
from pathlib import Path
from sqlalchemy import select
from fastapi import Request
from app.core.deps import SettingsDep, DbDep
from app.core.exceptions import BusinessException, credentials_exception
from app.core.logger import logger
from app.models import Track, User
from app.utils.metadata import parse_metadata
from app.utils.pinyin import get_artist_sort_fields
from app.utils.audiofile import AudioMeta
from app.services.processor import MusicFileProcessor

# def is_chinese(text: str) -> bool:
#     '''check if text contains chinese character'''
#     return any('\u4e00' <= char <= '\u9fff' for char in text)

class FileService:
    def __init__(self, settings: SettingsDep):
        self.settings = settings

    def _sanitize_filename(self, filename: str) -> str:
        '''exclude special characters from filename'''
        return re.sub(r'[\\/:*?"<>|]', '_', filename)
    
    async def save_temp_file(self, file_data: bytes, filename: str) -> Path:
        '''save file to temp directory, return file path'''
        safe_name = self._sanitize_filename(filename)
        temp_path = self.settings.TEMP_DIR / f'{uuid.uuid4().hex}_{safe_name}'
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(file_data)

    def create_staging_session(self) -> str:
        '''create staging session, return session_id'''
        session_id = str(uuid.uuid4())
        session_dir = self.settings.STAGING_DIR / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / 'songs').mkdir(parents=True, exist_ok=True)
        return session_id
    
    def list_sessions(self) -> list[dict]:
        '''list all staging sessions'''
        if not self.settings.STAGING_DIR.exists():
            return []
        sessions = []
        for item in self.settings.STAGING_DIR.iterdir():
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
        return sessions

    def move_single_to_staging(self, session_id: str, temp_file_id: str) -> str:
        '''move single file to staging session directory'''
        temp_file = self.settings.TEMP_DIR / temp_file_id
        if not temp_file.exists():
            raise FileNotFoundError(f'File {temp_file} not found')
        session_dir = self.settings.STAGING_DIR / session_id
        dest = session_dir / 'songs' / temp_file_id
        dest = self.settings.STAGING_DIR / session_id / 'songs' / temp_file.name
        try:
            shutil.move(str(temp_file), str(dest))
        except Exception as e:
            raise BusinessException(code=10050, msg='IO error', detail=f'Failed to move {temp_file} to {dest}: {e}')

    def move_all_to_staging(self, session_id: str) -> list[str]:
        '''move all files in the temp directory to staging session directory'''
        session_songs_dir = self.settings.STAGING_DIR / session_id / 'songs'
        moved_files = []

        for temp_file in self.settings.TEMP_DIR.iterdir():
            if temp_file.is_file():
                dest = session_songs_dir / temp_file.name
                try:
                    shutil.move(str(temp_file), str(dest))
                    moved_files.append(temp_file.name)
                except Exception as e:
                    logger.error(f'Failed to move {temp_file} to {dest}: {e}')
        return moved_files

    def list_session_files(self, session_id: str, moved: list[str] | None = None):
        '''list all files in the staging session directory'''
        session_songs_dir = self.settings.STAGING_DIR / session_id / 'songs'
        files = []
        if not session_songs_dir.exists():
            raise FileNotFoundError(f'Session {session_id} not found')
        for f in session_songs_dir.iterdir():
            if f.is_file():
                if moved is not None and not f.name in moved:
                    continue
                files.append(AudioMeta(str(f)).to_fileinfo())
        return list(map(lambda x: setattr(x, 'path', str(Path(x.path).relative_to(session_songs_dir))) or x, files))    

    def update_file_version(self, session_id: str, file_path: str, use_apev2: bool = False, del_id3v1: bool = True, del_apev2: bool = False):
        file_path = self.settings.STAGING_DIR / session_id / 'songs' / file_path
        audio_meta = AudioMeta(str(file_path))
        audio_meta.update_version(use_apev2, del_id3v1, del_apev2)

    def update_file_metatags(self, session_id: str, filename: str, new_meta: dict, del_id3v1: bool = True, del_apev2: bool = False):
        '''update file metadata'''
        from app.services.fetchcoverart import get_cover_art, clear_cached_cover
        file_path = self.settings.STAGING_DIR / session_id / 'songs' / filename
        release_id = new_meta.get('mb_albumid', None)
        print(new_meta.get('use_matched_cover', False), release_id)
        if new_meta.get('use_matched_cover', False) and release_id:
            cover_data = get_cover_art(release_id)
            if cover_data:
                new_meta['cover_art_data'] = cover_data
        audio_meta = AudioMeta(str(file_path))
        audio_meta.update_metadata(new_meta, del_id3v1, del_apev2)
        clear_cached_cover(release_id)

class ArchiveService:
    '''music archive service'''
    def __init__(self, db: DbDep, settings: SettingsDep, request: Request):
        self.db = db
        self.settings = settings
        self.current_user = request.state.user_id

    def _get_initial_group(self, initial: str) -> str:
        '''compute initial group name'''
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

    def _generate_target_path(self, lang: str, artist_name: str, album_title: str | None, track_title: str) -> Path:
        '''generate archive target path'''
        area = 'Chinese' if lang=='CN' else 'Foreign'
        _, initial = get_artist_sort_fields(artist_name)
        group = self._get_initial_group(initial)

        base = Path(self.settings.MUSIC_LIBRARY_PATH) / area / group / artist_name
        if album_title:
            return base / album_title / track_title
        else:
            return base / track_title

    async def archive_session(self, session_id: str, items: list[str], playlist: str, lang: str) -> list[str]:
        '''archive all the files in the staging session directory to its proper place in the music library'''
        session_dir = self.settings.STAGING_DIR / session_id
        songs_dir = session_dir / 'songs'
        errors = []
        results = []

        for item in items:
            song_file = songs_dir / item
            if song_file.suffix.lower() not in self.settings.MUSIC_FILE_EXTENSIONS:
                continue
            # 1. extract metadata(used for path generation)
            try:
                meta = parse_metadata(song_file)
            except Exception:
                errors.append(f'Failed to extract metadata from {song_file}')
                continue
            # 2. recognize the artist_name(used for path generation)
            artist_name = 'Unknown Artist'
            if meta['artists']:
                artist_name = meta['artists'][0]
            elif meta.get('albumartist'):
                artist_name = meta['albumartist'][0]
            # 3. recognize file name(track title first, then the filename)
            filename = (meta.get('title') + song_file.suffix) or song_file.name[33:] # trim the uuid ahead(32 chars)
            # 4. generate target path
            target_path = self._generate_target_path(lang, artist_name, meta.get('album'), filename)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            # 5. move file
            try:
                shutil.move(str(song_file), str(target_path))
                results.append((item, target_path)) # item is the relative path
            except Exception as e:
                errors.append(f'Failed to move {song_file} to {target_path}: {e}')
                continue

            # 6. triggle music file processor(archive to db)
            try:
                processor = MusicFileProcessor(self.settings.MUSIC_LIBRARY_PATH, self.db)
                await processor.process_single_file(target_path)
                await self.db.commit()
            except Exception as e:
                await self.db.rollback()
                errors.append(f'Failed to process {target_path}: {e}')
                continue
        # 7. delete session directory if empty
        if len(list(songs_dir.iterdir())) == 0:
            shutil.rmtree(str(songs_dir))
        if len(list(session_dir.iterdir())) == 0:
            shutil.rmtree(str(session_dir))
        # 8. if debug mode，record the target path of the moved files, for debug later
        if self.settings.DEBUG:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            with open(self.settings.LOG_DIR / 'archive.log', 'a', encoding='utf-8') as f:
                f.write(f'[{now}]{session_id} \n')
                for source, target in results:
                    f.write(f'{source} -> {target}\n')
        # 9. if playlist is not empty, create a json file according to the file target path, 
        # then a playlist can be created according to the json file
        if playlist and results:
            time = datetime.now().strftime('%Y%m%d%H%M%S')
            playlist_file = self.settings.PLAYLISTS_TMP_DIR / f'{playlist}_{time}.json'
            playlist_file.write_text(json.dumps(
                {
                    'title': playlist,
                    'username': self.current_user.username,
                    'source': 'staging',
                    'time': time,
                    'tracks': [str(filepath.relative_to(Path(self.settings.MUSIC_LIBRARY_PATH))) for _, filepath in results]
                }, 
                ensure_ascii=False), encoding='utf-8'
            )
        return errors
    
class StreamService:
    '''Music streaming service'''
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    async def get_audio_file(self, track_id: int) -> str | None:
        '''get audio file path for streaming'''
        result = await self.db.execute(select(Track.path).where(Track.id == track_id, Track.is_deleted == False))
        track_path = result.scalar_one_or_none()
        if not track_path:
            return None
        abs_path = (self.settings.MUSIC_LIBRARY_PATH / track_path).resolve()
        return str(abs_path)
    
    async def check_user(self, user_id: int):
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise credentials_exception