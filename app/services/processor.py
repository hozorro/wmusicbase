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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from typing import Any
from app.models import Genre, Artist, Album, Track, Folder, track_artists, track_genres
from app.utils.color import generate_unique_light_color
from app.utils.pinyin import get_artist_sort_fields
from app.utils.metadata import extract_metadata, extract_cover_art_hash
from logging import getLogger

logger = getLogger(__name__)

class MusicFileProcessor:
    def __init__(self, db:AsyncSession):
        self.db = db
        # 内存缓存：已处理的实体映射（减少数据查询）
        self.genre_cache: dict[str, 'Genre'] = {}   # {name: Genre}
        self.artist_cache: dict[str, 'Artist'] = {} # {name: Artist}
        self.album_cache: dict[tuple, 'Album'] = {} # {(title,album_artist_id): Album}
        self.folder_cache: dict[str, 'Folder'] = {} # {path: Folder}
        self.track_cache: dict[str, 'Track'] = {}   # {path: Track}
        self.genre_colors_cache: set[str] = set()
        # 已处理的文件路径集合（避免重复处理同一文件）
        self.processed_files: set[str] = set()
        self.logger = logger

    async def get_or_create_genre(self, name: str) -> Genre:
        '''获取或创建流派（利用缓存和数据库冲突处理）'''
        if name in self.genre_cache:
            return self.genre_cache[name]
        
        # 从数据库中获取流派
        result = await self.db.execute(select(Genre).where(Genre.name == name))
        genre = result.scalar_one_or_none()
        if genre: 
            self.genre_cache[name] = genre
            return genre
        
        color = generate_unique_light_color(self.genre_colors_cache)
        
        # 创建流派（冲突时忽略）
        try:
            stmt = pg_insert(Genre).values(
                name=name,
                color=color,
                info={}
            ).on_conflict_do_nothing(index_elements=['name'])
            await self.db.execute(stmt)
            await self.db.flush()
            # 重新查询确保并发场景下拿到最新的流派
            result = await self.db.execute(select(Genre).where(Genre.name == name))
            genre = result.scalar_one()
            self.genre_cache[name] = genre
            self.genre_colors_cache.add(color)
            return genre
        except IntegrityError as e: # 遇到 IntegrityError，说明数据库中已存在该记录
            self.logger.error(f'Failed to create genre {name}: {e}')
    
    async def get_or_create_artist(self, name: str, mbid: str | None) -> Artist:
        '''获取或创建艺术家（利用缓存和数据库冲突处理）'''
        if name in self.artist_cache:
            return self.artist_cache[name]
        
        # 从数据库中获取艺术家
        result = await self.db.execute(select(Artist).where(Artist.name == name))
        artist = result.scalar_one_or_none()
        if artist: 
            self.artist_cache[name] = artist
            return artist
        
        sort_name, pinyin_initial = get_artist_sort_fields(name)

        try:
            stmt = pg_insert(Artist).values(
                name=name,
                mb_artistid=mbid,
                sort_name=sort_name,
                pinyin_initial=pinyin_initial,
                info={}
            ).on_conflict_do_nothing(index_elements=['name'])
            await self.db.execute(stmt)
            await self.db.flush()
            result = await self.db.execute(select(Artist).where(Artist.name == name))
            artist = result.scalar_one()
            self.artist_cache[name] = artist
            return artist
        except IntegrityError as e: # 遇到 IntegrityError，说明数据库中已存在该记录
            self.logger.error(f'Failed to create artist {name}: {e}')
    
    async def get_or_create_album(self, title: str, year: int | None, mbid: str | None, album_artist: Artist) -> Album | None:
        '''获取或创建专辑（利用缓存和数据库冲突处理）'''
        if (title, album_artist.id) in self.album_cache:
            return self.album_cache[(title, album_artist.id)]
        
        # 从数据库中获取专辑
        result = await self.db.execute(select(Album).where(Album.title == title, Album.album_artist_id == album_artist.id))
        album = result.scalar_one_or_none()
        if album: 
            self.album_cache[(title, album_artist.id)] = album
            return album
        try:
            stmt = pg_insert(Album).values(
                title=title,
                year=year,
                mb_albumid=mbid,
                album_artist_id=album_artist.id
            ).on_conflict_do_nothing(index_elements=['title', 'album_artist_id'])
            await self.db.execute(stmt)
            await self.db.flush()
            result = await self.db.execute(select(Album).where(Album.title == title, Album.album_artist_id == album_artist.id))
            album = result.scalar_one()
            self.album_cache[(title, album_artist.id)] = album
            return album
        except IntegrityError as e: # 遇到 IntegrityError，说明数据库中已存在该记录
            self.logger.error(f'Failed to create album {title}: {e}')


    async def get_or_create_folder(self, path: Path, root_path: Path) -> Folder:
        '''获取或创建文件夹（利用缓存和数据库冲突处理）'''
        abs_path = str(path.resolve())
        if abs_path in self.folder_cache:
            return self.folder_cache[abs_path]
        
        # 从数据库中获取文件夹
        result = await self.db.execute(select(Folder).where(Folder.path == abs_path))
        folder = result.scalar_one_or_none()
        if folder: 
            self.folder_cache[abs_path] = folder
            return folder
        
        # 创建父目录
        parent_id = None
        if path != root_path:
            parent_folder = await self.get_or_create_folder(path.parent, root_path)
            parent_id = parent_folder.id

        try:
            stmt = pg_insert(Folder).values(path=abs_path, parent_id=parent_id).on_conflict_do_nothing(index_elements=['path'])
            await self.db.execute(stmt)
            await self.db.flush()
            result = await self.db.execute(select(Folder).where(Folder.path == abs_path))
            folder = result.scalar_one()
            self.folder_cache[abs_path] = folder
            return folder
        except IntegrityError as e:
            self.logger.error(f'❌Failed to create folder {str(path)}: {e}')
            raise
    
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
        '''更新已存在的Track及其关联关系'''
        # 1. 更新基础字段
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
        track.is_deleted = False # 若之前被软删除，恢复
        track.deleted_at = None

        # 2. 清除旧的多对多关系
        await self.db.execute(delete(track_artists).where(track_artists.c.track_id == track.id))
        await self.db.execute(delete(track_genres).where(track_genres.c.track_id == track.id))

        # 3. 重建多对多关系
        if artists:
            await self.db.execute(track_artists.insert().values([
                {'track_id': track.id, 'artist_id': artist.id} for artist in artists
            ]))
        if genres: 
            await self.db.execute(track_genres.insert().values([
                {'track_id': track.id, 'genre_id': genre.id} for genre in genres
            ]))
        await self.db.flush()
        return True

    async def process_single_file(self, file_path: Path, root_path: Path) -> bool:
        '''处理单个音乐文件，返回是否成功'''
        if file_path in self.processed_files: 
            return True

        meta = extract_metadata(file_path)
        if not meta: 
            self.logger.warning(f'❌Failed to extract metadata from {file_path}')
            return False
        
        # ===== 推导album_artist_name =====
        album_artist_name = None
        mb_albumartistid = None

        # 1. 优先使用albumartist（取第一个）
        albumartist_list = meta.get('albumartist', [])
        if albumartist_list and albumartist_list[0].strip():
            album_artist_name = albumartist_list[0].strip()
            mb_albumartistid_list = meta.get('mb_albumartistid', [])
            if mb_albumartistid_list:
                mb_albumartistid = mb_albumartistid_list[0].strip()

        # 2. fallback 到 artist（取第一个）
        if not album_artist_name:
            artist_list = meta['artists']
            if artist_list and artist_list[0].strip():
                album_artist_name = artist_list[0].strip()

        # 3. 最终 fallback
        if not album_artist_name: 
            album_artist_name = 'Unknown Artist'

        # ===== 创建各实体（按依赖顺序） =====
        # 1. 获取/处理/创建 Genre
        genres = []
        for genre_name in meta['genres']:
            genre_strip = genre_name.strip()
            if genre_strip: 
                genre = await self.get_or_create_genre(genre_strip)
                genres.append(genre)

        # 2. 获取/处理/创建 Artist
        artists = []
        for i, artist_name in enumerate(meta['artists']):
            artist_strip = artist_name.strip()
            if artist_strip:
                mbid = meta['mb_artistids'][i] if i < len(meta['mb_artistids']) else None
                artist = await self.get_or_create_artist(artist_strip, mbid)
                artists.append(artist)
        
        # 3. 获取/处理/创建 Album
        album_artist = await self.get_or_create_artist(album_artist_name.strip(), mb_albumartistid)
        album = await self.get_or_create_album(meta['album'], meta['year'], meta['mb_albumid'], album_artist)

        # 4. 获取/创建 Folder
        folder = await self.get_or_create_folder(file_path.parent, root_path)

        # 5. 计算封面hash
        cover_art_hash = extract_cover_art_hash(file_path)

        # 6. 创建/更新 Track
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
                path=str(file_path.resolve()),
                folder=folder,
                album=album,
                artists=artists,    # 自动处理多对多关系
                genres=genres       # 自动处理多对多关系
            )
            self.db.add(track)
            await self.db.flush()
            self.processed_files.add(file_path)
            return True