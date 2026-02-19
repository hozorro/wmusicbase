# -*- encoding: utf-8 -*-
'''
@File      :   artwork.py
@Time      :   2025/10/20 14:10:02
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   deal artwork of track, artist and album
'''


import re, aiofiles, hashlib
from pathlib import Path
from fastapi import UploadFile
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.models import Track, track_artists, Artist, Album, Playlist
from app.core.deps import SettingsDep, DbDep
from app.core.logger import logger
from app.utils.metadata import extract_embedded_artwork

# cache dir
COVER_FILENAME_PATTERNS = [
    r'^cover',
    r'^folder',
    r'^front',
    r'^back',
    r'^album',
    r'^artwork',
    r'^poster',
]
COVER_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp', 'bmp']
ARTIST_FACE_PATTERNS = COVER_FILENAME_PATTERNS + [r'^face']
ARTIST_PORTRAIT_PATTERNS = ['portrait.jpg', 'portrait.png']

class ArtworkService:
    """handle artwork of track, artist and album"""
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    async def _save_artwork_to_cache(self, id: int, img_cate: str, cover_data: bytes | Path, additional: str = '') -> Path | None:
        '''save artwork to cache(unified format with jpg, and compressed)'''
        if img_cate not in ['track', 'artist', 'album', 'playlist', 'tmp']: 
            logger.error(f'Invalid img_cate: {img_cate}')
            return None
        cache_dir = self.settings.ARTWORK_DIR / f'{img_cate}s'
        cache_path = cache_dir / (f'{id}_{additional}.jpg' if additional else f'{id}.jpg')
        try:
            img_data = cover_data
            if not type(cover_data) == bytes: # capatibale with old version
                async with aiofiles.open(str(cover_data.resolve()), 'rb') as f:
                    img_data = await f.read()
        
            # use pillow to unified format and compress the image(avoid big size image consuming unlimited store space)
            from PIL import Image
            from io import BytesIO
            with Image.open(BytesIO(img_data)) as img:
                max_width = 784
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                img_byte_arr = BytesIO()
                img.convert('RGB').save(img_byte_arr, format='JPEG', quality=90)
                img_byte_arr = img_byte_arr.getvalue()

            # async write files
            async with aiofiles.open(cache_path, 'wb') as f:
                await f.write(img_byte_arr)
            logger.info(f'Saved artwork of {img_cate}_{id} to cache: {cache_path}')
            return cache_path
        except Exception as e:
            logger.error(f'Failed to save artwork of {img_cate}_{id} to cache: {e}')
            return None
    async def get_or_cache_track_artwork(self, track_id: int) -> Path | None:
        '''
        get or cache artwork of track。
        return cached file path if exists else None
        '''
        cache_path = self.settings.TRACK_ARTWORK_DIR / f'{track_id}.jpg'
        default_artwork_path = self.settings.TRACK_ARTWORK_DIR / 'default.jpg'

        # 1. check cache
        if cache_path.exists():
            # optional: verify the hash compare with cover art hash
            return cache_path
        
        # 2. get track from db
        result = await self.db.execute(select(Track).where(Track.id == track_id))
        track = result.scalar_one_or_none()
        if not track or not track.cover_art_hash:
            return default_artwork_path # None or default
        
        # 3. extract embedded artwork
        track_path = self.settings.MUSIC_LIBRARY_PATH / track.path
        image_data = extract_embedded_artwork(str(track_path))
        if not image_data:
            return default_artwork_path # None or default
        
        # 4. save as jpeg file(unified image size)
        try:
            img_path = await self._save_artwork_to_cache(track_id, 'track', image_data)
            return img_path if img_path else None
        except Exception:
            return default_artwork_path # None or default
    
    def invalidate_artwork_cache(self, id: int, art_type: str, art_type_additional: str = '') -> bool:
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
                logger.info(f'Invalidated artwork cache for track {id}')
                return True
            except Exception as e:
                logger.error(f'Failed to delete artwork cache for track {id}: {e}')
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

                artist_dir = music_root / lang / group / artist_name
                if artist_dir.is_dir():
                    return artist_dir
                
        return None

    async def find_artist_image_in_directory(self, artist_name: str, img_cate: str) -> Path | None:
        '''
        finde artist image in the artist directory
        Args:
            artist_name (str): artist name
            img_cate (str): image type, face or portrait
        Returns:
            Path | None: image path, or None if not found
        '''
        music_root = Path(self.settings.MUSIC_LIBRARY_PATH)
        for lang in ['Chinese', 'Foreign']:
            for group in ['A-G', 'H-N', 'O-T', 'U-Z', 'Z_']:
                artist_dir = music_root / lang / group / artist_name
                if not artist_dir.is_dir(): continue

                try:
                    for entry in artist_dir.iterdir():
                        if entry.is_file():
                            file_name = entry.stem.lower()
                            file_ext = entry.suffix.lower()

                            if file_ext in COVER_EXTENSIONS:
                                for pattern in (ARTIST_FACE_PATTERNS if img_cate == 'face' else ARTIST_PORTRAIT_PATTERNS):
                                    if re.match(pattern, file_name, re.IGNORECASE):
                                        return entry
                except Exception as e:
                    logger.error(f'Failed to scan artist directory to find artist artwork in {artist_dir}: {e}')
        return None

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
            raise Exception(f'Artist {artist_id} not found')
        content = await image_file.read()
        # whether the artist has directory
        if self.has_artist_directory(artist.name): 
            artist_dir = self.get_artist_directory(artist.name)
            img_path = artist_dir / ('artist.jpg' if img_cate == 'face' else 'portrait.jpg')
            # async write file
            async with aiofiles.open(img_path, 'wb') as f: 
                await f.write(content)
            self.invalidate_artwork_cache(artist.id, 'artist', img_cate)
        else: 
            img_path = self._save_artwork_to_cache(artist.id, 'artist', content, img_cate)
        # update cover_art_hash used for the front end cache refresh, same for album, playlist, track.
        cover_art_hash = hashlib.sha1(content).hexdigest()
        artist.cover_art_hash = cover_art_hash
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

    def get_album_directory(self, album: Album) -> Path:
        '''get album directory'''
        return Path(album.tracks[0].path).parent

    async def find_album_cover_in_directory(self, album: Album) -> Path | None:
        '''find cover.jpg / folder.jpg in the album directory'''
        # infer the album directory from any track
        # assume all the track of the album are in the same directory
        if not album.tracks: return None

        music_root = Path(self.settings.MUSIC_LIBRARY_PATH)
        track_path = music_root / album.tracks[0].path
        album_dir = track_path.parent
        try:
            for entry in album_dir.iterdir():
                if entry.is_file():
                    file_name = entry.stem.lower()
                    file_ext = entry.suffix.lower()

                    if file_ext in COVER_EXTENSIONS:
                        for pattern in COVER_FILENAME_PATTERNS:
                            if re.match(pattern, file_name, re.IGNORECASE):
                                return entry
        except Exception as e:
            logger.error(f'Failed to find album cover for album {album.id} in album directory: {e}')
        return None

    async def get_or_cache_album_artwork(self, album_id: int) -> Path | None:
        '''
        get or cache album artwork
        priority: cover of album dir -> extracted cover art of track -> None
        '''
        cache_path = self.settings.ALBUM_ARTWORK_DIR / f'{album_id}.jpg'
        if cache_path.exists(): return cache_path

        # 1. get album, preload tracks
        result = await self.db.execute(select(Album).where(Album.id == album_id).options(selectinload(Album.tracks)))
        album = result.scalars().first()
        if not album or not album.tracks:
            return None
        
        # 2. first: find cover.jpg / folder.jpg in the album directory
        dir_cover = await self.find_album_cover_in_directory(album)
        if dir_cover:
            try: 
                cache_path = await self._save_artwork_to_cache(album_id, 'album', dir_cover)
                if cache_path: return cache_path
            except Exception as e:
                logger.error(f'Failed to save album cover for album {album_id} from directory: {e}')

        # 3. fallback: get the cover art of the track(the first one)
        for track in album.tracks:
            if track.cover_art_hash:
                cache_path = await self.get_or_cache_track_artwork(track.id)
                if cache_path: 
                    return cache_path
                
        # 4. fallback: default image
        default_img = self.settings.ALBUM_ARTWORK_DIR / 'default.jpg'
        if default_img.exists(): 
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
            raise Exception('album not found')
        content= await image_file.read()
        if self.has_album_directory(album): 
            album_dir = self.get_album_directory(album)
            img_path = album_dir / 'cover.jpg'
            async with aiofiles.open(img_path, 'wb') as f: 
                await f.write(content)
            # clear cache（ensure getting the latest cover at next request）
            self.invalidate_artwork_cache(album.id, 'album')
        else: 
            img_path = self._save_artwork_to_cache(album.id, 'album', content)
        cover_art_hash = hashlib.sha1(content).hexdigest()
        album.cover_art_hash = cover_art_hash
        await self.db.commit()
        return img_path
    
    async def get_or_cache_playlist_artwork(self, playlist_id: int | str) -> Path | None:
        '''get or cache playlist artwork'''
        cache_path = self.settings.PLAYLIST_ARTWORK_DIR / f'{playlist_id}.jpg'
        if cache_path.exists(): 
            return cache_path
        return self.settings.PLAYLIST_ARTWORK_DIR / 'default.jpg'
    
    async def save_uploaded_playlist_image(self, playlist_id: int, image_file) -> Path | None:
        '''save uploaded playlist image'''
        playlist = await self.db.get(Playlist, playlist_id)
        if not playlist: 
            raise Exception('playlist not found')
        content= await image_file.read()
        img_path = await self._save_artwork_to_cache(playlist_id, 'playlist', content)
        cover_art_hash = hashlib.sha1(content).hexdigest()
        playlist.cover_art_hash = cover_art_hash
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
        
        try:
            img_path = await self._save_artwork_to_cache(name, 'tmp', image_data)
            return img_path if img_path else None
        except Exception:
            logger.error(f'Failed to save artwork for tmp track {file_path}')        