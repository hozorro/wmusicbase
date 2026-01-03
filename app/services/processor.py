# -*- encoding: utf-8 -*-
'''
@File      :   processor.py
@Time      :   2025/10/21 17:07:58
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   music file processor
'''


from pathlib import Path
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.core.logger import logger
from app.core.db import retry_deadlock
from app.models import Genre, Artist, Album, Track, Folder, track_artists, track_genres
from app.utils.color import generate_unique_light_color
from app.utils.pinyin import get_artist_sort_fields
from app.utils.metadata import extract_metadata, extract_cover_art_hash
from typing import Any

class MusicFileProcessor:
    def __init__(self, root_path: Path, db: AsyncSession):
        self.db = db
        self.root_path = root_path
        # memory cache：handled entity matches(avoid duplicate processing)
        self.genre_cache: dict[str, 'Genre'] = {}   # {name: Genre}
        self.artist_cache: dict[str, 'Artist'] = {} # {name: Artist}
        self.album_cache: dict[tuple, 'Album'] = {} # {(title,album_artist_id): Album}
        self.folder_cache: dict[str, 'Folder'] = {} # {path: Folder}
        self.track_cache: dict[str, 'Track'] = {}   # {path: Track}
        self.genre_colors_cache: set[str] = set()
        # handled file paths set(avoid duplicate processing)
        self.processed_files: set[str] = set()
        self.logger = logger

    @retry_deadlock(max_retries=3)
    async def get_or_create_genre(self, name: str) -> Genre | None:
        '''get or create genre(use cache and database conflict handling)'''
        if name in self.genre_cache:
            return self.genre_cache[name]
        
        # get genre from database
        result = await self.db.execute(select(Genre).where(Genre.name == name))
        genre = result.scalar_one_or_none()
        if genre: 
            self.genre_cache[name] = genre
            return genre
        
        color = generate_unique_light_color(self.genre_colors_cache)
        
        # create genre(ignore when conflict)
        stmt = pg_insert(Genre).values(
            name=name,
            color=color,
            info={}
        ).on_conflict_do_nothing(index_elements=['name']).returning(Genre)
        result = await self.db.execute(stmt)
        genre = result.scalar_one_or_none()
        # lookup again to ensure get the latest genre at concurrency scenario
        if not genre:
            result = await self.db.execute(select(Genre).where(Genre.name == name))
            genre = result.scalar_one()

        self.genre_cache[name] = genre
        self.genre_colors_cache.add(color)
        return genre

    @retry_deadlock(max_retries=3)
    async def get_or_create_artist(self, name: str, mbid: str | None) -> Artist | None:
        '''get or create artist(use cache and database conflict handling)'''
        if name in self.artist_cache:
            return self.artist_cache[name]
        
        # get artist from database
        result = await self.db.execute(select(Artist).where(Artist.name == name))
        artist = result.scalar_one_or_none()
        if artist: 
            self.artist_cache[name] = artist
            return artist
        
        sort_name, pinyin_initial = get_artist_sort_fields(name)

        stmt = pg_insert(Artist).values(
            name=name,
            mb_artistid=mbid,
            sort_name=sort_name,
            pinyin_initial=pinyin_initial,
            info={}
        ).on_conflict_do_nothing(index_elements=['name']).returning(Artist)
        result = await self.db.execute(stmt)
        artist = result.scalar_one_or_none()
        
        if not artist:
            result = await self.db.execute(select(Artist).where(Artist.name == name))
            artist = result.scalar_one()
        self.artist_cache[name] = artist
        return artist

    @retry_deadlock(max_retries=3)
    async def get_or_create_album(self, title: str, year: int | None, mbid: str | None, album_artist: Artist) -> Album | None:
        '''get or create album(use cache and database conflict handling)'''
        if (title, album_artist.id) in self.album_cache:
            return self.album_cache[(title, album_artist.id)]
        
        # get album from database
        result = await self.db.execute(select(Album).where(Album.title == title, Album.album_artist_id == album_artist.id))
        album = result.scalar_one_or_none()
        if album: 
            self.album_cache[(title, album_artist.id)] = album
            return album

        stmt = pg_insert(Album).values(
            title=title,
            year=year,
            mb_albumid=mbid,
            album_artist_id=album_artist.id
        ).on_conflict_do_nothing(index_elements=['title', 'album_artist_id']).returning(Album)
        result = await self.db.execute(stmt)
        album = result.scalar_one_or_none()

        if not album:
            result = await self.db.execute(select(Album).where(Album.title == title, Album.album_artist_id == album_artist.id))
            album = result.scalar_one()
        self.album_cache[(title, album_artist.id)] = album
        return album

    @retry_deadlock(max_retries=3)
    async def get_or_create_folder(self, path: Path, root_path: Path) -> Folder | None:
        '''get or create folder(use cache and database conflict handling)'''
        rel_path = str(path.relative_to(self.root_path))
        if rel_path in self.folder_cache:
            return self.folder_cache[rel_path]
        
        # get folder from database
        result = await self.db.execute(select(Folder).where(Folder.path == rel_path))
        folder = result.scalar_one_or_none()
        if folder: 
            self.folder_cache[rel_path] = folder
            return folder
        
        # create parent folder
        parent_id = None
        if path != root_path:
            parent_folder = await self.get_or_create_folder(path.parent, root_path)
            parent_id = parent_folder.id

        stmt = pg_insert(Folder).values(
            path=rel_path, parent_id=parent_id
        ).on_conflict_do_nothing(index_elements=['path']).returning(Folder)
        result = await self.db.execute(stmt)
        folder = result.scalar_one_or_none()

        if not folder:
            result = await self.db.execute(select(Folder).where(Folder.path == rel_path))
            folder = result.scalar_one()
        self.folder_cache[rel_path] = folder
        return folder
    
    async def update_track(
        self,
        track: Track,
        meta: dict[str, Any],
        cover_art_hash: str | None,
        folder: Folder,
        album: Album | None,
        artists: list[Artist],
        genres: list[Genre]
    ) -> bool:
        '''update the existed track's metadata and relations'''
        try:
            # 1. update basic info
            track.title = meta['title']
            track.duration = meta['duration']
            track.bitrate = meta['bitrate']
            track.bitrate_mode = meta['bitrate_mode']
            track.year = meta['year']
            track.acoustid_id = meta['acoustid_id']
            track.mb_trackid = meta['mb_trackid']
            track.cover_art_hash = cover_art_hash
            track.folder = folder
            track.album = album
            track.is_deleted = False # if the track is deleted, set it to False as soft delete
            track.deleted_at = None

            # 2. clear old many to many relations
            await self.db.execute(delete(track_artists).where(track_artists.c.track_id == track.id))
            await self.db.execute(delete(track_genres).where(track_genres.c.track_id == track.id))

            # 3. rebuild many to many relations
            if artists:
                await self.db.execute(track_artists.insert().values([
                    {'track_id': track.id, 'artist_id': artist.id} for artist in artists
                ]))
            if genres: 
                await self.db.execute(track_genres.insert().values([
                    {'track_id': track.id, 'genre_id': genre.id} for genre in genres
                ]))
            await self.db.flush()
            self.logger.debug(f'✅Updated track {track.title} ({track.id}) successfully.')
            return True
        except Exception as e: # other exceptions, indicating database operation failure
            self.logger.error(f'❌Failed to update track {track.id}: {e}')
            self.db.rollback()
            return False

    @retry_deadlock(max_retries=3)
    async def process_single_file(self, file_path: Path) -> bool:
        '''process single file, return True if success'''
        if file_path in self.processed_files: 
            return True

        meta = extract_metadata(file_path)
        if not meta: 
            self.logger.warning(f'❌Failed to extract metadata from {file_path}')
            return False
        
        # ===== infer album_artist_name =====
        album_artist_name = None
        mb_albumartistid = None

        # 1. first use albumartist(the first one)
        albumartist_list = meta.get('albumartist', [])
        if albumartist_list:
            album_artist_name = albumartist_list[0]
            album_artist_name = album_artist_name.strip() if album_artist_name else None
            mb_albumartistid_list = meta.get('mb_albumartistid', [])
            if mb_albumartistid_list:
                mb_albumartistid = mb_albumartistid_list[0].strip() if mb_albumartistid_list[0] else None

        # 2. fallback to artist(the first one)
        if not album_artist_name:
            artist_list = meta['artists']
            if artist_list:
                album_artist_name = artist_list[0].strip() if artist_list[0] else None

        # 3. final fallback
        if not album_artist_name: 
            album_artist_name = 'Unknown Artist'

        # ===== create each entity (sequence is important) =====
        # 1. get/handle/create Genre
        genres = []
        for genre_name in meta['genres']:
            genre_strip = genre_name.strip() if genre_name else None
            if genre_strip: 
                genre = await self.get_or_create_genre(genre_strip)
                if genre:
                    genres.append(genre)

        # 2. get/handle/create Artist
        artists = []
        for i, artist_name in enumerate(meta['artists']):
            artist_strip = artist_name.strip() if artist_name else None
            if artist_strip:
                mbid = meta['mb_artistids'][i] if i < len(meta['mb_artistids']) else None
                artist = await self.get_or_create_artist(artist_strip, mbid)
                if artist:
                    artists.append(artist)
        
        # 3. get/handle/create Album
        # handle album title, if empty, set default title with “Unknown Album(album artist name)”
        album_name = meta['album'].strip() if meta['album'] else f'Unknown Album({album_artist_name})'
        album_artist = await self.get_or_create_artist(album_artist_name, mb_albumartistid)
        if album_artist:
            album = await self.get_or_create_album(album_name, meta['year'], meta['mb_albumid'], album_artist)

        # 4. get/create Folder
        folder = await self.get_or_create_folder(file_path.parent, self.root_path)

        # 5. comput cover art hash
        cover_art_hash = extract_cover_art_hash(file_path)

        # 6. create/update Track
        result = await self.db.execute(select(Track).where(Track.path == str(file_path.resolve())))
        track = result.scalar_one_or_none()
        if track:
            await self.update_track(track, meta, cover_art_hash, folder, album, artists, genres)
        else:
            track = Track(
                title=meta['title'],
                duration=meta['duration'],
                bitrate=meta['bitrate'],
                bitrate_mode=meta['bitrate_mode'],
                year=meta['year'],
                acoustid_id=meta['acoustid_id'],
                mb_trackid=meta['mb_trackid'],
                cover_art_hash=cover_art_hash,
                path=str(file_path.relative_to(self.root_path)),
                folder=folder,
                album=album,
                artists=artists,    # handle many to many relations automatically
                genres=genres       # handle many to many relations automatically
            )
            self.db.add(track)
            self.processed_files.add(file_path)
            return True
