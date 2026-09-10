# -*- encoding: utf-8 -*-
'''
@File      :   artwork.py
@Time      :   2025/10/20 14:10:02
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   deal artwork of track, artist and album
'''


import re, aiofiles, hashlib, shutil, time
from pathlib import Path
from enum import Enum
from fastapi import UploadFile
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.core.exceptions import BusinessException
from app.models import Track, track_artists, Artist, Album, Playlist
from app.core.deps import SettingsDep, DbDep
from app.core.logger import logger
from app.utils import image
from app.utils.metadata import extract_embedded_artwork
from app.utils.image import resize_image
from app.utils.common import sanitize_folder_name

# cache dir
COVER_FILENAME_PATTERNS = [ # match with sequence
    re.compile(r'^cover', re.I),
    re.compile(r'^folder', re.I),
    re.compile(r'^front', re.I),
    re.compile(r'^back', re.I),
    re.compile(r'^album', re.I),
    re.compile(r'^artwork', re.I),
    re.compile(r'^poster', re.I),
]
COVER_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', 'bmp']
ARTIST_PORTRAIT_PATTERNS = ['portrait.jpg', 'portrait.png']

class ArtType(str, Enum):
    TRACK = 'track'
    ARTIST = 'artist'
    ALBUM = 'album'
    PLAYLIST = 'playlist'

class ArtworkService:
    """handle artwork of track, artist and album"""
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    async def _save_artwork_to_cache(self, id: int, art_type: ArtType, cover_data: bytes | Path, additional: str = '') -> Path | None:
        '''save artwork to cache(unified format with jpg, and compressed)'''
        if art_type not in ['track', 'artist', 'album', 'playlist', 'tmp']: 
            logger.error(f'Invalid img_cate: {art_type}')
            return None
        cache_dir = self.settings.ARTWORK_DIR / f'{art_type}s'
        cache_path = cache_dir / (f'{id}_{additional}.jpg' if additional else f'{id}.jpg')
        try:
            img_data = cover_data
            if not type(cover_data) == bytes: # capatibale with old version
                async with aiofiles.open(str(cover_data.resolve()), 'rb') as f:
                    img_data = await f.read()
        
            # use pillow to unified format and compress the image(avoid big size image consuming unlimited store space)
            img_byte_arr = resize_image(img_data)

            # async write files
            async with aiofiles.open(cache_path, 'wb') as f:
                await f.write(img_byte_arr)
            logger.info(f'Saved artwork of {art_type}_{id} to cache: {cache_path}')
            return cache_path
        except Exception as e:
            logger.error(f'Failed to save artwork of {art_type}_{id} to cache: {e}')
            return None

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        '''compute SHA1 hash of a static artwork file (unified hash criterion)'''
        h = hashlib.sha1()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

    async def get_or_cache_track_artwork(self, track_id: int) -> Path | None:
        '''
        get or cache artwork of track。
        return cached file path if exists else None
        '''
        cache_path = self.settings.TRACK_ARTWORK_DIR / f'{track_id}.jpg'

        # 1. check cache
        if cache_path.exists():
            return cache_path
        
        
        result = await self.db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if track:
            track_path = self.settings.MUSIC_LIBRARY_PATH / track.path
            # 2. try to extract embedded artwork directly
            # (do not rely on track.cover_art_hash here: it is only written
            # after the static file is generated, so it may be None even if
            # the audio file has an embedded cover)
            image_data = None
            try:
                image_data = extract_embedded_artwork(str(track_path))
            except Exception as e:
                logger.error(f'Failed to extract embedded artwork from {track_path}.')
                
            if image_data:
                # save as jpeg file(unified image size)
                img_path = await self._save_artwork_to_cache(track_id, 'track', image_data)
                if img_path:
                    return img_path
            # 3. try to use album artwork
            album_path = track_path.parent
            img_path = await self.find_album_cover_in_directory(album_path)
            if img_path: # use album artwork if exists
                img_path = await self._save_artwork_to_cache(track_id, 'track', img_path)
                return img_path
                
        # 4. try to use default artwork
        default_artwork_path = self.settings.TRACK_ARTWORK_DIR / 'default.jpg'
        if default_artwork_path.exists(): # use default artwork if exists
            return default_artwork_path
        return None

    async def sync_track_artwork(self, track_id: int) -> str | None:
        '''
        unconditionally regenerate the track artwork static file and keep
        cover_art_hash consistent with it (hash <-> static file same lifecycle).
        used after a track file is created/modified by the watcher.
        Returns:
            the new cover_art_hash, or None when no static file is generated
        '''
        result = await self.db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track:
            logger.warning(f'sync_track_artwork: track {track_id} not found')
            return None

        # 1. remove old static file (track artwork is always overwritten)
        self.invalidate_artwork_cache(track_id, 'track')
        # 2. regenerate
        cache_path = await self.get_or_cache_track_artwork(track_id)
        # 3. update hash according to the static file existence
        if cache_path:
            track.cover_art_hash = self.compute_file_hash(cache_path)
            return track.cover_art_hash
        return None

    async def ensure_album_artwork(self, album_id: int) -> str | None:
        '''
        generate the album artwork static file only when it is missing
        (skip if exists), and keep cover_art_hash consistent with it.
        Returns:
            the cover_art_hash, or None when no static file exists
        '''
        album = await self.db.get(Album, album_id)
        if not album:
            logger.warning(f'ensure_album_artwork: album {album_id} not found')
            return None

        static_path = self.settings.ALBUM_ARTWORK_DIR / f'{album_id}.jpg'
        if not static_path.exists():
            await self.get_or_cache_album_artwork(album_id)
        album.cover_art_hash = self.compute_file_hash(static_path) if static_path.exists() else None
        return album.cover_art_hash

    async def ensure_artist_artwork(self, artist_id: int) -> None:
        '''
        generate the artist face/portrait artwork static files only when they
        are missing (skip if exist), and keep face_art_hash/portrait_art_hash
        consistent with them.
        '''
        artist = await self.db.get(Artist, artist_id)
        if not artist:
            logger.warning(f'ensure_artist_artwork: artist {artist_id} not found')
            return

        for img_cate in ('face', 'portrait'):
            static_path = self.settings.ARTIST_ARTWORK_DIR / f'{artist_id}_{img_cate}.jpg'
            if not static_path.exists():
                await self.get_or_cache_artist_artwork(artist_id, img_cate)
            new_hash = self.compute_file_hash(static_path) if static_path.exists() else None
            if img_cate == 'face':
                artist.face_art_hash = new_hash
            else:
                artist.portrait_art_hash = new_hash

    async def sync_artworks_after_track_change(self, rel_path: str) -> None:
        '''
        sync artworks after a track file is created/modified (watcher entry):
        - track artwork: always regenerated (with cover_art_hash)
        - album/artist artworks: generated only when the static file is missing
        order matters: track -> album -> artist
        (album/artist fallbacks depend on track artworks and cover_art_hash)
        Args:
            rel_path: track path relative to MUSIC_LIBRARY_PATH
        '''
        result = await self.db.execute(
            select(Track)
            .where(Track.path == rel_path)
            .options(selectinload(Track.artists), selectinload(Track.album))
        )
        track = result.scalar_one_or_none()
        if not track:
            logger.warning(f'sync_artworks_after_track_change: track not found: {rel_path}')
            return

        # 1. track artwork (always update)
        await self.sync_track_artwork(track.id)
        # 2. album artwork (skip if exists)
        if track.album_id:
            await self.ensure_album_artwork(track.album_id)
        # 3. artist artworks (skip if exist), including the album artist
        artist_ids = {artist.id for artist in track.artists}
        if track.album and track.album.album_artist_id:
            artist_ids.add(track.album.album_artist_id)
        for artist_id in artist_ids:
            await self.ensure_artist_artwork(artist_id)
    
    def invalidate_artwork_cache(self, id: int, art_type: ArtType, art_type_additional: str = '') -> bool:
        '''
        invalidate artwork cache(if exists)
        Args:
            id (int): id of the entity of the artwork
            art_type (str): entity type, 'track', 'artist', 'album'
            art_type_additional (str, optional): addtional param, 
            e.g. art_type_additional with 'face' means face type artwork of artist. empty as default.
        Returns:
            bool: whether deleted successfully, True for deleted, False for the file not exists
        '''
        if art_type not in ['track', 'artist', 'album']: 
            logger.error(f'Invalid art_type: {art_type}')
            return False
        if art_type == 'track':
            cache_path = self.settings.TRACK_ARTWORK_DIR / f'{id}.jpg'
        elif art_type == 'artist':
            cache_path = self.settings.ARTIST_ARTWORK_DIR / f'{id}_{art_type_additional}.jpg'
        elif art_type == 'album':
            cache_path = self.settings.ALBUM_ARTWORK_DIR / f'{id}.jpg'

        if cache_path.exists():
            try:
                cache_path.unlink()
                logger.info(f'Invalidated artwork cache for {art_type} {id}')
                return True
            except Exception as e:
                logger.error(f'Failed to delete artwork cache for {art_type} {id}: {e}')
                return False
        return False

    def has_artist_directory(self, artist_name: str) -> bool:
        '''
        check if artist directory exists
        Args:
            artist_name (str): artist name
        Returns:
            bool: exists or not
        '''
        music_root = Path(self.settings.MUSIC_LIBRARY_PATH)
        for lang in ['Chinese', 'Foreign']:
            lang_path = music_root / lang
            if not lang_path.exists(): continue

            for group in ['A-G', 'H-N', 'O-T', 'U-Z', 'Z_']:
                group_path = lang_path / group
                if not group_path.exists(): continue

                artist_dir = group_path / artist_name
                if artist_dir.is_dir():
                    logger.info(f'Found artist directory: {artist_dir}')
                    return True
        logger.warning(f'Artist directory not found for artist: {artist_name}')
        return False

    def get_artist_directory(self, artist_name: str) -> Path | None:
        '''
        get artist directory
        Args:
            artist_name (str): artist name
        Returns:
            Path | None: artist directory path, or None if not found
        '''
        music_root = Path(self.settings.MUSIC_LIBRARY_PATH)
        for lang in ['Chinese', 'Foreign']:
            lang_path = music_root / lang
            if not lang_path.exists(): continue

            for group in ['A-G', 'H-N', 'O-T', 'U-Z', 'Z_']:
                group_path = lang_path / group
                if not group_path.exists(): continue

                artist_dir = music_root / lang / group / sanitize_folder_name(artist_name)
                if artist_dir.is_dir():
                    return artist_dir
                
        return None

    async def find_artist_image_in_directory(self, artist_name: str, img_cate: str) -> Path | None:
        '''
        find artist image in the artist directory
        looks for files named {img_cate}_{N}.jpg and returns the one with lowest N
        Args:
            artist_name (str): artist name
            img_cate (str): image type, face or portrait
        Returns:
            Path | None: image path, or None if not found
        '''
        artist_dir = self.get_artist_directory(artist_name)
        if not artist_dir:
            return None

        # pattern: face_1.jpg, face_2.jpg, portrait_1.jpg, etc.
        pattern = re.compile(rf'^{img_cate}_(\d+)\.(jpg|jpeg|png)$', re.I)
        candidates = []

        for entry in artist_dir.iterdir():
            if entry.is_file():
                match = pattern.match(entry.name)
                if match:
                    num = int(match.group(1))
                    candidates.append((num, entry))

        if not candidates:
            return None

        # sort by number and return the lowest
        candidates.sort(key=lambda x: x[0])
        return candidates[0][1]

    async def get_artist_art_candidates(self, artist_id: int, art_type: str) -> list[str]:
        '''
        get candidate artwork filenames for an artist
        returns list of filenames matching {art_type}_N.jpg pattern, naturally sorted
        '''
        artist = await self.db.get(Artist, artist_id)
        if not artist:
            raise ValueError(f'Artist {artist_id} not found')
        artist_dir = self.get_artist_directory(artist.name)
        if not artist_dir:
            return []
        pattern = re.compile(rf'^{art_type}_(\d+)\.(jpg|jpeg|png)$', re.I)
        candidates = []
        for entry in artist_dir.iterdir():
            if entry.is_file():
                match = pattern.match(entry.name)
                if match:
                    candidates.append((int(match.group(1)), entry.name))
        candidates.sort(key=lambda x: x[0])
        return [name for _, name in candidates]

    def _find_lowest_available_number(self, existing_numbers: list[int]) -> int:
        '''find the lowest positive integer not in the list'''
        s = set(existing_numbers)
        n = 1
        while n in s:
            n += 1
        return n

    async def upload_artist_art_candidate(self, artist_id: int, art_type: str, content: bytes) -> str:
        '''
        upload a candidate artwork image to the artist directory
        finds the lowest available number gap and saves with that number
        returns the new filename
        '''
        artist = await self.db.get(Artist, artist_id)
        if not artist:
            raise ValueError(f'Artist {artist_id} not found')
        artist_dir = self.get_artist_directory(artist.name)
        if not artist_dir:
            raise ValueError(f'Artist directory not found for {artist.name}')
        # find existing numbers
        pattern = re.compile(rf'^{art_type}_(\d+)\.(jpg|jpeg|png)$', re.I)
        existing_numbers = []
        for entry in artist_dir.iterdir():
            if entry.is_file():
                match = pattern.match(entry.name)
                if match:
                    existing_numbers.append(int(match.group(1)))
        # find lowest gap
        new_num = self._find_lowest_available_number(existing_numbers)
        # determine extension from content (default to jpg)
        ext = 'jpg'
        filename = f'{art_type}_{new_num}.{ext}'
        file_path = artist_dir / filename
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        return filename

    async def set_artist_art_from_candidate(self, artist_id: int, art_type: str, filename: str) -> str:
        '''
        set an artist's official artwork from a candidate file
        swaps the selected candidate to position _1 (renumbering the old _1 if needed)
        updates the cache and the corresponding *_art_hash
        returns the artwork URL
        '''
        artist = await self.db.get(Artist, artist_id)
        if not artist:
            raise ValueError(f'Artist {artist_id} not found')
        artist_dir = self.get_artist_directory(artist.name)
        if not artist_dir:
            raise ValueError(f'Artist directory not found for {artist.name}')
        # validate filename format
        pattern = re.compile(rf'^{art_type}_(\d+)\.(jpg|jpeg|png)$', re.I)
        match = pattern.match(filename)
        if not match:
            raise ValueError(f'Invalid filename format: {filename}')
        selected_num = int(match.group(1))
        selected_path = artist_dir / filename
        if not selected_path.exists():
            raise ValueError(f'Candidate file not found: {filename}')
        face_path = artist_dir / f'{art_type}_1.jpg'
        if face_path.exists() and selected_num != 1:
            # need to move current _1 out of the way
            existing_numbers = []
            for entry in artist_dir.iterdir():
                if entry.is_file():
                    m = pattern.match(entry.name)
                    if m:
                        existing_numbers.append(int(m.group(1)))
            # remove selected_num from the list (it will be renamed to _1)
            existing_numbers.remove(selected_num)
            # find lowest gap for the displaced _1
            gap_num = self._find_lowest_available_number(existing_numbers)
            # rename current _1 to the gap position
            shutil.move(str(face_path), str(artist_dir / f'{art_type}_{gap_num}.jpg'))
        # rename selected candidate to _1 (skip if already _1)
        if selected_num != 1:
            shutil.move(str(selected_path), str(face_path))
        # invalidate old cache
        self.invalidate_artwork_cache(artist_id, 'artist', art_type)
        # save new _1 to cache and compute hash from the static file
        cache_path = await self._save_artwork_to_cache(artist_id, 'artist', face_path, art_type)
        cover_art_hash = self.compute_file_hash(cache_path) if cache_path else None
        if art_type == 'face':
            artist.face_art_hash = cover_art_hash
        else:
            artist.portrait_art_hash = cover_art_hash
        await self.db.commit()
        return f'/api/v1/artwork/artist/{artist_id}?img_cate={art_type}&t={int(time.time())}'

    async def get_artist_candidate_file(self, artist_id: int, filename: str) -> Path | None:
        '''
        get a candidate artwork file path for an artist (with security validation)
        returns the file path if valid, None otherwise
        '''
        # validate filename to prevent path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            return None
        # validate file extension
        if not Path(filename).suffix.lower() in ['.jpg', '.jpeg', '.png']:
            return None
        artist = await self.db.get(Artist, artist_id)
        if not artist:
            return None
        artist_dir = self.get_artist_directory(artist.name)
        if not artist_dir:
            return None
        file_path = artist_dir / filename
        if not file_path.is_file():
            return None
        return file_path

    async def find_common_track_artwork(self, artist_id: int) -> Path | None:
        '''
        lookup all the track artwork cache of the artist, find the most common one
        Args:
            artist_id (int): artist id
        Returns:
            Path | None: image path, or None if not found
        '''
        # lookup all the cover_art_hash of the tracks of the artist and the count of each cover_art_hash
        stmt = (
            select(Track.cover_art_hash, func.count(Track.id).label('cnt'))
            .join(track_artists, Track.id == track_artists.c.track_id)
            .where(track_artists.c.artist_id == artist_id)
            .where(Track.cover_art_hash.isnot(None))
            .group_by(Track.cover_art_hash)
            .order_by(func.count(Track.id).desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        row = result.fetchone()

        if not row or not row.cover_art_hash: return None

        # lookup the track id of any track with the most common cover_art_hash(max count)
        track_stmt = select(Track.id).where(Track.cover_art_hash == row.cover_art_hash).limit(1)
        track_result = await self.db.execute(track_stmt)
        track_id = track_result.scalar_one_or_none()

        if track_id is None: return None

        # get the cached track artwork
        cache_path = await self.get_or_cache_track_artwork(track_id)
        return cache_path if cache_path else None

    async def get_or_cache_artist_artwork(self, artist_id: int, img_cate: str = 'face') -> Path | None:
        '''
        get or cache artist artwork
        return the cached artist artwork path if exists, or None if not found
        Args:
            artist_id (int): artist id
            img_cate (str): image type, face or portrait
        Returns:
            Path | None: image path, or None if not found
        '''
        cache_path = self.settings.ARTIST_ARTWORK_DIR / f'{artist_id}_{img_cate}.jpg'
        if cache_path.exists(): return cache_path

        # try 1：fetch artist cover from directory（only when the artist directory exists）
        artist = await self.db.get(Artist, artist_id)
        dir_img = await self.find_artist_image_in_directory(artist.name, img_cate)
        if dir_img:
            logger.info(f'Found artist cover in directory: {dir_img}')
            cache_path = await self._save_artwork_to_cache(artist_id, 'artist', dir_img, img_cate)
            if cache_path: return cache_path
            
        # try 2：find the most common track artwork of the artist
        common_img = await self.find_common_track_artwork(artist_id)
        if common_img:
            logger.info(f'Found common track artwork for artist {artist_id}: {common_img}')
            cache_path = await self._save_artwork_to_cache(artist_id, 'artist', common_img, img_cate)
            if cache_path: return cache_path
        
        # try 3：use default image
        default_img = self.settings.ARTIST_ARTWORK_DIR / ('default_face.jpg' if img_cate == 'face' 
                                                        else 'default_portrait.jpg')
        if default_img.exists(): 
            # save default image to cache to avoid the 2 steps above for every artist artwork request
            cache_path = await self._save_artwork_to_cache(artist_id, 'artist', default_img, img_cate)
            if cache_path: return cache_path
        
        return None

    async def save_uploaded_artist_image(self, artist_id: int, img_cate: str, image_file: UploadFile) -> Path | None:
        '''
        save uploaded artist image:
        - if the artist has directory, save as artist.jpg in the artist directory
        - else save as artist_id.jpg to the artist artwork cache directory
        '''
        artist = await self.db.get(Artist, artist_id)
        if not artist:
            raise BusinessException(
                code=30104, 
                msg=f'artist {artist_id} not found', 
                status_code=status.HTTP_404_NOT_FOUND
            )
        content = await image_file.read()
        # whether the artist has directory
        artist_dir = self.get_artist_directory(artist.name)
        if artist_dir is not None: 
            img_path = artist_dir / ('face.jpg' if img_cate == 'face' else 'portrait.jpg')
            # async write file
            async with aiofiles.open(img_path, 'wb') as f: 
                await f.write(content)
        # generate/update the static artwork file
        img_path = await self._save_artwork_to_cache(artist.id, 'artist', content, img_cate)
        # update the corresponding hash field based on img_cate
        # (hash of the static file, consistent with the whole project)
        cover_art_hash = self.compute_file_hash(img_path) if img_path else None
        if img_cate == 'face':
            artist.face_art_hash = cover_art_hash
        else:  # portrait
            artist.portrait_art_hash = cover_art_hash
        await self.db.commit()
        return img_path

    def has_album_directory(self, album: Album) -> bool:
        '''
        whether the album has directory, True if satisfied the two conditions:
        - the album has any track with the track.path's parent folder name == album.title
        - album.title do not starts with "Unknown"
        '''
        if not album.tracks: return False

        # exclude the album title starts with "Unknown"
        if album.title.startswith('Unknown'): return False

        # any track of the album with the track.path's parent folder name == album title
        # (assume that all the track of the album is in the same directory)
        return Path(album.tracks[0].path).parent.name == album.title

    def get_album_directory(self, album: Album) -> Path | None:
        '''get album directory'''
        try:
            return Path(album.tracks[0].path).parent
        except:
            return None

    async def find_album_cover_in_directory(self, album_dir: Path) -> Path | None:
        '''
        find cover.jpg / folder.jpg in the album directory and all subdirectories
        recursively scans the directory tree for image files matching cover patterns
        '''
        full_album_dir = self.settings.MUSIC_LIBRARY_PATH / album_dir
        if not full_album_dir.exists():
            return None

        # recursively find all image files in the album directory tree
        candidates = []
        for entry in full_album_dir.rglob('*'):
            if entry.is_file() and entry.suffix.lower() in COVER_EXTENSIONS:
                candidates.append(entry)

        if not candidates:
            return None

        # find the best match based on filename patterns (cover > folder > front > ...)
        best_match = None
        best_weight = len(COVER_FILENAME_PATTERNS)
        for c in candidates:
            lower_name = c.stem.lower()
            for index, pattern in enumerate(COVER_FILENAME_PATTERNS):
                if pattern.match(lower_name):
                    if index < best_weight:
                        best_match = c
                        best_weight = index
                    break

        return best_match

    async def get_or_cache_album_artwork(self, album_id: int) -> Path | None:
        '''
        get or cache album artwork
        priority: cover of album dir -> extracted cover art of track -> None
        '''
        cache_path = self.settings.ALBUM_ARTWORK_DIR / f'{album_id}.jpg'
        if cache_path.exists(): return cache_path

        # 1. get album, preload tracks
        result = await self.db.execute(
            select(Album)
            .where(Album.id == album_id)
            .options(
                selectinload(Album.tracks)
                .load_only(Track.path, Track.cover_art_hash)
            ))
        album = result.scalars().first()
        if not album or not album.tracks:
            return None
        
        # 2. first: find cover.jpg / folder.jpg in the album directory
        album_dir = self.get_album_directory(album)
        if album_dir:
            dir_cover = await self.find_album_cover_in_directory(album_dir)
            if dir_cover:
                cache_path = await self._save_artwork_to_cache(album_id, 'album', dir_cover)
                if cache_path: return cache_path

        # 3. fallback: get the cover art of the track(the first one)
        for track in album.tracks:
            if track.cover_art_hash:
                track_cover_path = await self.get_or_cache_track_artwork(track.id)
                if track_cover_path: 
                    cache_path = await self._save_artwork_to_cache(album_id, 'album', track_cover_path)
                    if cache_path: return cache_path
                
        # 4. fallback: default image
        default_img = self.settings.ALBUM_ARTWORK_DIR / 'default.jpg'
        if default_img.exists(): 
            # need to cache to avoid the 3 steps above for every album artwork request
            cache_path = await self._save_artwork_to_cache(album_id, 'album', default_img)
            if cache_path: 
                return cache_path
            
        return None

    async def save_uploaded_album_image(self, album_id: int, image_file) -> Path | None:
        '''
        save uploaded album image:
        - if the album has directory, save as cover.jpg in the album directory
        - else save as album_id.jpg to the album artwork cache directory
        '''
        album = await self.db.get(Album, album_id)
        if not album: 
            raise BusinessException(
                code=30204, 
                msg='album not found', 
                status_code=status.HTTP_404_NOT_FOUN
            )
        content= await image_file.read()
        if self.has_album_directory(album): 
            album_dir = self.get_album_directory(album)
            img_path = album_dir / 'cover.jpg'
            async with aiofiles.open(img_path, 'wb') as f: 
                await f.write(content)
        # generate/update the static artwork file
        img_path = await self._save_artwork_to_cache(album.id, 'album', content)
        # hash of the static file, consistent with the whole project
        album.cover_art_hash = self.compute_file_hash(img_path) if img_path else None
        await self.db.commit()
        return img_path
    
    async def get_or_cache_playlist_artwork(self, playlist_id: int | str) -> Path | None:
        '''get or cache playlist artwork'''
        cache_path = self.settings.PLAYLIST_ARTWORK_DIR / f'{playlist_id}.jpg'
        if cache_path.exists(): 
            return cache_path
        default_img = self.settings.PLAYLIST_ARTWORK_DIR / 'default.jpg'
        if default_img.exists(): 
            # no need to save to cache
            return default_img
        return None
    
    async def save_uploaded_playlist_image(self, playlist_id: int, image_file) -> Path | None:
        '''save uploaded playlist image'''
        playlist = await self.db.get(Playlist, playlist_id)
        if not playlist: 
            raise BusinessException(
                code=30504, 
                msg='playlist not found', 
                status_code=status.HTTP_404_NOT_FOUND
            )
        content= await image_file.read()
        img_path = await self._save_artwork_to_cache(playlist_id, 'playlist', content)
        # hash of the static file, consistent with the whole project
        playlist.cover_art_hash = self.compute_file_hash(img_path) if img_path else None
        await self.db.commit()
        return img_path
    
    async def get_or_cache_tmp_track_artwork(self, file_path: str) -> Path | None:
        '''
        get or cache staging track artwork
        file_path: absolute path of the staging track
        '''
        name = Path(file_path).stem
        cache_path = self.settings.TMP_ARTWORK_DIR / f'{name}.jpg'
        if cache_path.exists(): 
            return cache_path
        
        image_data = extract_embedded_artwork(file_path)
        if not image_data: 
            return None
        
        img_path = await self._save_artwork_to_cache(name, 'tmp', image_data)
        return img_path
    
    async def get_default_art(self, art_type: ArtType) -> Path | None:
        if art_type == 'artist':
            default_art = (self.settings.ARTWORK_DIR / 'artists' / 'default_face.jpg').resolve()
        else:
            default_art = (self.settings.ARTWORK_DIR / f'{art_type}s' / 'default.jpg').resolve()
        if default_art.exists(): 
            return default_art
        return None
    async def set_default_art(self, art_type: ArtType, cover: UploadFile) -> None:
        try:
            cover_data = await cover.read()

            img_byte_arr = resize_image(cover_data, 1024)

            default_path = self.settings.ARTWORK_DIR / f'{art_type}s' / 'default.jpg'
            async with aiofiles.open(default_path, 'wb') as f: 
                await f.write(img_byte_arr)
            logger.info(f'Set default {art_type} artwork')
        except Exception as e: 
            logger.error(f'Failed to set default {art_type} artwork.')
            raise e