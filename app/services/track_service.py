# -*- encoding: utf-8 -*-
'''
@File      :   track_service.py
@Time      :   2025/11/29 21:23:05
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   track service
'''


import asyncio
import math
import random
from datetime import datetime
from fastapi import Request, status
from sqlalchemy import select, func, desc, nulls_last
from sqlalchemy.orm import selectinload, load_only, joinedload
from app.core.deps import SettingsDep, DbDep
from app.core.exceptions import BusinessException
from app.core.logger import logger
from app.models import Track, track_artists, track_genres, Artist, Album, TrackFav, TrackHit, PlaylistTrack
from app.services.lyric_index_service import read_lyric_file
from app.utils.audiofile import AudioMeta
from app.utils.streaming import signer

# 首页「最近添加 / 最常播放」条数：后端、前端 URL、SW/IDB 三方共用 16
HOME_TRACK_COUNT = 16

# 与前端 idb/sw-api/endpoints/tracks.ts 的 clampInt / clampWeight 口径一致
RANDOM_NUM_MAX = 200
SCATTER_M_CAP = 20
SCATTER_N_CAP = 200


def clamp_tracks_num(num: int) -> int:
    return min(RANDOM_NUM_MAX, max(1, int(num)))


def normalize_pool(pool: int) -> int:
    '''pool 夹到 100~1000 后按 100 取整；half-up 与 JS Math.round 对齐'''
    rounded = math.floor(int(pool) / 100 + 0.5) * 100
    return min(1000, max(100, rounded))


def clamp_weight(weight: int) -> int:
    '''2→0.25 弱偏向 · 5→1 线性 · 9→2 强偏向'''
    return min(9, max(2, int(weight)))


def weight_alpha(weight: int) -> float:
    return (clamp_weight(weight) - 1) / 4


def weighted_sample(items: list[tuple[int, float]], k: int) -> list[int]:
    '''Efraimidis-Spirakis 加权不放回抽样：key = U^(1/w)，取 top-k'''
    scored = [(random.random() ** (1.0 / max(w, 1e-9)), item_id) for item_id, w in items]
    scored.sort(reverse=True)
    return [item_id for _, item_id in scored[:min(k, len(scored))]]

class TrackService:
    def __init__(self, db: DbDep, settings: SettingsDep, request: Request):
        self.db = db
        self.settings = settings
        self.current_user_id = request.state.user_id

    # region backend use
    async def _update_track_file_tag(self, file_path: str, data: dict):
        audio_meta = AudioMeta(file_path)
        audio_meta.update_metadata(data)

    async def update_track_cover(self, track_id: int, cover_data: bytes) -> None:
        '''write cover art image bytes into the track file tag, then regenerate static artwork and update hash'''
        from app.services.artwork_service import ArtworkService
        track = await self.db.get(Track, track_id)
        if not track:
            raise BusinessException(
                code=30308,
                msg=f'track not exists: {track_id}',
                detail={'track_id': track_id},
                status_code=status.HTTP_404_NOT_FOUND
            )
        track_path = str((self.settings.MUSIC_LIBRARY_PATH / track.path).resolve())
        # write cover art into the audio file tag
        audio_meta = AudioMeta(track_path)
        audio_meta.update_metadata({'cover_art_data': cover_data})
        # regenerate static artwork file and update cover_art_hash
        artwork_service = ArtworkService(self.db, self.settings)
        new_hash = await artwork_service.sync_track_artwork(track_id)
        if new_hash:
            track.cover_art_hash = new_hash
            await self.db.commit()

    async def update_tracks_field_tag(self, track_ids: list[int], field: str, value: str | int | list[str]) -> list[dict]:
        '''update track field tag, used for batch editing'''
        tracks = await self.db.execute(select(Track).where(Track.id.in_(track_ids)))
        track_paths = [track.path for track in tracks.scalars()]
        errors = []
        for track_path in track_paths:
            try:
                track_path_abs = str((self.settings.MUSIC_LIBRARY_PATH / track_path).resolve())
                await self._update_track_file_tag(track_path_abs, {field: value})
            except Exception as e:
                errors.append({
                    'track_path': track_path,
                    'error': str(e)
                })
                continue
        return errors
    
    # endregion backend use

    # region frontend use
    async def create_signed_url(self, tid: int):
        raw = f'{tid}:{self.current_user_id}'
        token = signer.sign(raw).decode()
        return f'stream/{tid}?token={token}'

    async def get_track_info(self, track_id: int) -> Track | None:
        """
        get track info:
        - basic field: id/title/duration
        - artists: id/name
        - album: id/title
        - hit count: played times of the current user
        - favorited: whether the current user favorited the track
        """
        hit_subq = (
            select(
                TrackHit.track_id,
                func.count(TrackHit.id).label('hit_count')
            ).group_by(TrackHit.track_id)
            .where(TrackHit.user_id == self.current_user_id)
            .subquery()
        )
        fav_subq = (
            select(
                TrackFav.track_id,
                TrackFav.favorited_at,
            ).where(
                TrackFav.track_id == track_id, 
                TrackFav.user_id == self.current_user_id
            ).subquery()
        )
        stmt = (
            select(
                Track,
                func.coalesce(hit_subq.c.hit_count, 0).label('hit_count'),
                func.coalesce(fav_subq.c.favorited_at, None).label('favorited_at')
            )
            .outerjoin(hit_subq, Track.id == hit_subq.c.track_id)
            .outerjoin(fav_subq, Track.id == fav_subq.c.track_id)
            .where(Track.id == track_id, Track.is_deleted == False)
            .options(
                load_only(Track.id, Track.title, Track.duration, Track.cover_art_hash),
                selectinload(Track.artists).load_only(Artist.id, Artist.name, Artist.face_art_hash, Artist.portrait_art_hash),
                joinedload(Track.album).load_only(Album.id, Album.title, Album.cover_art_hash),
            )
        )
        result = await self.db.execute(stmt)
        row = result.first()
        if not row:
            return None
        
        track, hit_count, favorited_at = row
        track.hit_count = hit_count
        track.favorited_at = favorited_at
        return track
    
    async def get_track_more_info(self, track_id: int) -> Track | None:
        stmt = select(Track).where(Track.id == track_id)
        result = await self.db.execute(stmt)
        track = result.scalar_one_or_none()
        if not track:
            return None
        return track
    
    async def get_random_tracks(self, limit: int = 20):
        '''get random tracks'''
        stmt = (
            select(Track)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
            .where(Track.is_deleted == False)
            .order_by(func.random())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def get_artist_random_tracks(self, artist_id: int, limit: int = 20):
        '''get random tracks of an artist'''
        stmt = (
            select(Track).options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
            .join(track_artists, Track.id == track_artists.c.track_id)
            .where(track_artists.c.artist_id == artist_id, Track.is_deleted == False)
            .order_by(func.random())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def get_genre_random_tracks(self, genre_id: int, limit: int = 20):
        '''get random tracks of an genre'''
        stmt = (
            select(Track).options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
            .join(track_genres, Track.id == track_genres.c.track_id)
            .where(Track.is_deleted == False, track_genres.c.genre_id == genre_id)
            .order_by(func.random())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def get_favorite_tracks(self, limit: int = 100):
        '''get user favorite tracks'''
        stmt = (
            select(Track)
            .join(TrackFav, Track.id == TrackFav.track_id)
            .where(TrackFav.user_id == self.current_user_id, Track.is_deleted == False)
            .order_by(TrackFav.favorited_at.desc())
            .limit(limit)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks

    async def get_favorite_ids(self, limit: int = 100):
        '''get user favorite track ids'''
        stmt = (
            select(TrackFav.track_id)
            .where(TrackFav.user_id == self.current_user_id, TrackFav.favorited_at != None)
            .order_by(TrackFav.favorited_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        track_ids = result.scalars().all()
        return track_ids
    
    async def get_most_played_tracks(self, limit: int = HOME_TRACK_COUNT):
        '''get user most played tracks'''
        hit_count_subq = (
            select(
                TrackHit.track_id,
                func.count(TrackHit.id).label('total_hit_count')
            )
            .where(TrackHit.user_id == self.current_user_id)
            .group_by(TrackHit.track_id).subquery()
        )
        main_stmt = (
            select(Track)
            .outerjoin(hit_count_subq, Track.id == hit_count_subq.c.track_id)
            .where(Track.is_deleted == False)
            .order_by(
                desc(func.coalesce(hit_count_subq.c.total_hit_count, 0)),
                nulls_last(desc(Track.updated_at))
            )
            .limit(limit)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )
        
        result = await self.db.execute(main_stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def get_latest_added_tracks(self, num: int = HOME_TRACK_COUNT):
        '''get latest added tracks'''
        stmt = (
            select(Track)
            .where(Track.is_deleted == False)
            .order_by(Track.created_at.desc())
            .limit(num)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def _get_album_tracks(self, album_id: int):
        '''get album tracks'''
        result = await self.db.execute(
            select(Track)
            .where(Track.album_id == album_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100) # limit 100 to avoid too many tracks
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )
        tracks = result.scalars().all()
        return tracks
    
    async def _get_artist_tracks(self, artist_id: int):
        '''get artist tracks'''
        result = await self.db.execute(
            select(Track)
            .join(track_artists, Track.id == track_artists.c.track_id)
            .where(track_artists.c.artist_id == artist_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100) # limit 100 to avoid too many tracks
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )
        tracks = result.scalars().all()
        return tracks
    
    async def _get_genre_tracks(self, genre_id: int):
        '''get genre tracks'''
        result = await self.db.execute(
            select(Track)
            .join(track_genres, Track.id == track_genres.c.track_id)
            .where(track_genres.c.genre_id == genre_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100) # limit 100 to avoid too many tracks
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )
        tracks = result.scalars().all()
        return tracks
    
    async def _get_playlist_tracks(self, playlist_id: int):
        '''get playlist tracks'''
        result = await self.db.execute(
            select(Track)
            .join(PlaylistTrack, Track.id == PlaylistTrack.track_id)
            .where(PlaylistTrack.playlist_id == playlist_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100) # limit 100 to avoid too many tracks
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )
        tracks = result.scalars().all()
        return tracks
    
    async def _get_folder_tracks(self, folder_id: int):
        '''get folder tracks'''
        result = await self.db.execute(
            select(Track)
            .where(Track.folder_id == folder_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )
        tracks = result.scalars().all()
        return tracks
    
    async def get_collection_tracks(self, collection_type: str, collection_id: int):
        '''get collection tracks, collection can be album/artist/genre'''
        if collection_type == 'album':
            return await self._get_album_tracks(collection_id)
        elif collection_type == 'artist':
            return await self._get_artist_tracks(collection_id)
        elif collection_type == 'genre':
            return await self._get_genre_tracks(collection_id)
        elif collection_type == 'playlist':
            return await self._get_playlist_tracks(collection_id)
        elif collection_type == 'folder':
            return await self._get_folder_tracks(collection_id)
        else:
            return []

    async def get_lyric(self, track_id: int) -> str:
        '''lyric text of a track, read from the .lrc file next to the audio file

        an empty string means the track has no lyric yet. fetching is owned by
        the lyric index pipeline (lyrics table + fetcher), never done on demand
        here, so the disk file and the indexed row can not drift apart.
        '''
        track_path = (await self.db.execute(
            select(Track.path).where(Track.id == track_id)
        )).scalar_one_or_none()
        if track_path is None:
            return ''

        lyric_path = (self.settings.MUSIC_LIBRARY_PATH / track_path).with_suffix('.lrc')
        if not await asyncio.to_thread(lyric_path.exists):
            return ''
        return await asyncio.to_thread(read_lyric_file, lyric_path) or ''

    async def get_tracks_hit_time(self) -> list[datetime]:
        result = await self.db.execute(
            select(TrackHit.played_at)
        )
        return [dt for dt, in result.all()]

    # region 全部曲目 / 高级随机端点（与前端 SW/IDB 同契约）
    @staticmethod
    def _brief_options():
        '''TrackBrief 所需列与关系，避免随机/分页查询整表物化'''
        return (
            load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
            selectinload(Track.artists).load_only(Artist.id, Artist.name),
            joinedload(Track.album).load_only(Album.id, Album.title),
        )

    def _hit_stats_subq(self):
        '''当前用户的播放次数与最后播放时间（hot / history 排序共用）'''
        return (
            select(
                TrackHit.track_id,
                func.count(TrackHit.id).label('hit_count'),
                func.max(TrackHit.played_at).label('last_hit_at'),
            )
            .where(TrackHit.user_id == self.current_user_id)
            .group_by(TrackHit.track_id)
            .subquery()
        )

    async def get_sorted_tracks(self, sort: str, page: int, page_size: int) -> tuple[int, list[Track]]:
        '''latest=created_at DESC / hot=播放次数 DESC（含 0 次）/ history=最后播放 DESC（仅含播放过）'''
        stats = self._hit_stats_subq()
        base = select(Track).outerjoin(stats, Track.id == stats.c.track_id).where(Track.is_deleted == False)
        count_stmt = (
            select(func.count(Track.id))
            .select_from(Track)
            .outerjoin(stats, Track.id == stats.c.track_id)
            .where(Track.is_deleted == False)
        )
        if sort == 'hot':
            order_by = (desc(func.coalesce(stats.c.hit_count, 0)), desc(Track.id))
        elif sort == 'history':
            base = base.where(stats.c.last_hit_at.is_not(None))
            count_stmt = count_stmt.where(stats.c.last_hit_at.is_not(None))
            order_by = (desc(stats.c.last_hit_at), desc(Track.id))
        else:
            order_by = (desc(Track.created_at), desc(Track.id))

        total = (await self.db.execute(count_stmt)).scalar_one()
        offset = (page - 1) * page_size
        if offset >= total:
            return total, []
        stmt = base.order_by(*order_by).offset(offset).limit(page_size).options(*self._brief_options())
        result = await self.db.execute(stmt)
        return total, list(result.scalars().all())

    async def get_rnd_fresh_tracks(self, num: int, pool: int) -> list[Track]:
        '''候选池 = 最近添加的 pool 首，再随机抽 num 首（曲库不足按实际数量）'''
        ids_stmt = (
            select(Track.id)
            .where(Track.is_deleted == False)
            .order_by(desc(Track.created_at), desc(Track.id))
            .limit(pool)
        )
        ids = list((await self.db.execute(ids_stmt)).scalars().all())
        if not ids:
            return []
        stmt = (
            select(Track)
            .where(Track.id.in_(ids))
            .order_by(func.random())
            .limit(min(clamp_tracks_num(num), len(ids)))
            .options(*self._brief_options())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_rnd_artist_scattered_tracks(self, num: int, numpa: int) -> list[Track]:
        '''洗牌歌手 → 每位随机取 ≤m 首 → 去重填满 n 首'''
        m = min(SCATTER_M_CAP, max(1, int(numpa)))
        n = min(SCATTER_N_CAP, max(m + 1, int(num)))
        artists_stmt = (
            select(track_artists.c.artist_id)
            .join(Track, Track.id == track_artists.c.track_id)
            .where(Track.is_deleted == False)
            .group_by(track_artists.c.artist_id)
        )
        artist_ids = list((await self.db.execute(artists_stmt)).scalars().all())
        random.shuffle(artist_ids)

        picked_ids: set[int] = set()
        picked: list[Track] = []
        for artist_id in artist_ids:
            if len(picked) >= n:
                break
            clauses = [track_artists.c.artist_id == artist_id, Track.is_deleted == False]
            if picked_ids:
                clauses.append(~Track.id.in_(picked_ids))
            stmt = (
                select(Track)
                .join(track_artists, Track.id == track_artists.c.track_id)
                .where(*clauses)
                .order_by(func.random())
                .limit(min(m, n - len(picked)))
                .options(*self._brief_options())
            )
            for track in (await self.db.execute(stmt)).scalars().all():
                if track.id in picked_ids:
                    continue
                picked_ids.add(track.id)
                picked.append(track)
        return picked

    async def get_rnd_unhit_tracks(self, num: int) -> list[Track]:
        '''当前用户从未播放过的曲目（TrackHit 无记录）'''
        hit_ids = select(TrackHit.track_id).where(TrackHit.user_id == self.current_user_id)
        stmt = (
            select(Track)
            .where(Track.is_deleted == False, ~Track.id.in_(hit_ids))
            .order_by(func.random())
            .limit(clamp_tracks_num(num))
            .options(*self._brief_options())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_rnd_weighted_artist_tracks(self, num: int, weight: int) -> list[Track]:
        '''加权随机歌手（权重 = 曲目数^α），每人随机一首，展平成 Track[]'''
        counts_stmt = (
            select(track_artists.c.artist_id, func.count(track_artists.c.track_id).label('track_count'))
            .join(Track, Track.id == track_artists.c.track_id)
            .where(Track.is_deleted == False)
            .group_by(track_artists.c.artist_id)
        )
        rows = (await self.db.execute(counts_stmt)).all()
        alpha = weight_alpha(weight)
        artist_ids = weighted_sample(
            [(row.artist_id, max(1, row.track_count) ** alpha) for row in rows],
            clamp_tracks_num(num),
        )
        picked_ids: set[int] = set()
        picked: list[Track] = []
        for artist_id in artist_ids:
            clauses = [track_artists.c.artist_id == artist_id, Track.is_deleted == False]
            if picked_ids:
                clauses.append(~Track.id.in_(picked_ids))
            stmt = (
                select(Track)
                .join(track_artists, Track.id == track_artists.c.track_id)
                .where(*clauses)
                .order_by(func.random())
                .limit(1)
                .options(*self._brief_options())
            )
            track = (await self.db.execute(stmt)).scalars().first()
            if track is not None and track.id not in picked_ids:
                picked_ids.add(track.id)
                picked.append(track)
        return picked

    async def get_rnd_weighted_hit_tracks(self, num: int, weight: int) -> list[Track]:
        '''加权随机曲目（权重 = (1 + 播放次数)^α），未播放恒为 1，保留加权序'''
        stats = self._hit_stats_subq()
        rows_stmt = (
            select(Track.id, func.coalesce(stats.c.hit_count, 0).label('hit_count'))
            .select_from(Track)
            .outerjoin(stats, Track.id == stats.c.track_id)
            .where(Track.is_deleted == False)
        )
        rows = (await self.db.execute(rows_stmt)).all()
        alpha = weight_alpha(weight)
        picked_ids = weighted_sample(
            [(row.id, (1 + row.hit_count) ** alpha) for row in rows],
            clamp_tracks_num(num),
        )
        if not picked_ids:
            return []
        stmt = select(Track).where(Track.id.in_(picked_ids)).options(*self._brief_options())
        by_id = {t.id: t for t in (await self.db.execute(stmt)).scalars().all()}
        return [by_id[i] for i in picked_ids if i in by_id]
    # endregion 全部曲目 / 高级随机端点

    # endregion frontend use