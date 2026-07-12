# -*- encoding: utf-8 -*-
'''
@File      :   track_service.py
@Time      :   2025/11/29 21:23:05
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   track service
'''


import aiofiles, requests
from datetime import datetime, timezone
from fastapi import Request, HTTPException
from sqlalchemy import select, func, desc, nulls_last, delete
from sqlalchemy.orm import selectinload, load_only, joinedload
from app.core.deps import SettingsDep, DbDep
from app.core.logger import logger
from app.models import Track, track_artists, track_genres, Artist, Album, TrackFav, TrackHit, PlaylistTrack
from app.utils.audiofile import AudioMeta
from app.utils.streaming import signer

class TrackService:
    def __init__(self, db: DbDep, settings: SettingsDep, request: Request):
        self.db = db
        self.settings = settings
        self.current_user_id = request.state.user_id

    # region backend use
    async def _update_track_file_tag(self, file_path: str, data: dict):
        audio_meta = AudioMeta(file_path)
        audio_meta.update_metadata(data)

    async def update_tracks_field_tag(self, track_ids: list[int], field: str, value: str | int | list[str]) -> list[str]:
        '''update track field tag, used for batch editing'''
        tracks = await self.db.execute(select(Track).where(Track.id.in_(track_ids)))
        track_paths = [track.path for track in tracks.scalars()]
        errors = []
        for track_path in track_paths:
            try:
                self._update_track_file_tag(track_path, {field: value})
            except Exception as e:
                errors.append(f'Failed to update metadata for {track_path}: {e}')
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
    
    async def get_random_tracks(self, limit: int = 20) -> list[Track]:
        '''get random tracks'''
        stmt = (
            select(Track)
            .options(
                load_only(Track.id, Track.title),
                selectinload(Track.artists).load_only(Artist.name)
            )
            .where(Track.is_deleted == False)
            .order_by(func.random())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def get_artist_random_tracks(self, artist_id: int, limit: int = 20) -> list[Track]:
        '''get random tracks of an artist'''
        stmt = (
            select(Track).options(
                load_only(Track.id, Track.title),
            )
            .join(track_artists, Track.id == track_artists.c.track_id)
            .where(track_artists.c.artist_id == artist_id, Track.is_deleted == False)
            .order_by(func.random())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def get_genre_random_tracks(self, genre_id: int, limit: int = 20) -> list[Track]:
        '''get random tracks of an genre'''
        stmt = (
            select(Track).options(
                load_only(Track.id, Track.title),
            )
            .join(track_genres, Track.id == track_genres.c.track_id)
            .where(Track.is_deleted == False, track_genres.c.genre_id == genre_id)
            .order_by(func.random())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def get_favorite_tracks(self, limit: int = 100) -> list[Track]:
        '''get user favorite tracks'''
        stmt = (
            select(Track)
            .join(TrackFav, Track.id == TrackFav.track_id)
            .where(TrackFav.user_id == self.current_user_id, Track.is_deleted == False)
            .order_by(TrackFav.favorited_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def get_most_played_tracks(self, limit: int | None = 12) -> list[Track]:
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
                load_only(Track.id, Track.title, Track.cover_art_hash),
                selectinload(Track.artists).load_only(Artist.name),
            )
        )
        
        result = await self.db.execute(main_stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def get_latest_added_tracks(self, num: int = 12) -> list[Track]:
        '''get latest added tracks'''
        stmt = (
            select(Track)
            .where(Track.is_deleted == False)
            .order_by(Track.created_at.desc())
            .limit(num)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash),
                selectinload(Track.artists).load_only(Artist.name),
            )
        )
        result = await self.db.execute(stmt)
        tracks = result.scalars().all()
        return tracks
    
    async def favorite_track(self, track_id: int, is_favorited: bool) -> datetime | None:
        '''favorite or unfavorite a track'''
        favorited_at = None
        if is_favorited:
            existing_fav = await self.db.execute(
                select(TrackFav).where(TrackFav.user_id == self.current_user_id, TrackFav.track_id == track_id)
            )
            if existing_fav.scalar_one_or_none():
                return True  # already favorited
            new_fav = TrackFav(user_id=self.current_user_id, track_id=track_id)
            favorited_at = datetime.now(timezone.utc)
            new_fav.favorited_at = favorited_at
            self.db.add(new_fav)
        else:
            await self.db.execute(
                delete(TrackFav).where(TrackFav.user_id == self.current_user_id, TrackFav.track_id == track_id)
            )
        await self.db.commit()
        return favorited_at
    
    async def _get_album_tracks(self, album_id: int) -> list[Track]:
        '''get album tracks'''
        result = await self.db.execute(
            select(Track)
            .where(Track.album_id == album_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100) # limit 100 to avoid too many tracks
            .options(load_only(Track.id, Track.title))
        )
        tracks = result.scalars().all()
        return tracks
    
    async def _get_artist_tracks(self, artist_id: int) -> list[Track]:
        '''get artist tracks'''
        result = await self.db.execute(
            select(Track)
            .join(track_artists, Track.id == track_artists.c.track_id)
            .where(track_artists.c.artist_id == artist_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100) # limit 100 to avoid too many tracks
            .options(load_only(Track.id, Track.title))
        )
        tracks = result.scalars().all()
        return tracks
    
    async def _get_genre_tracks(self, genre_id: int) -> list[Track]:
        '''get genre tracks'''
        result = await self.db.execute(
            select(Track)
            .join(track_genres, Track.id == track_genres.c.track_id)
            .where(track_genres.c.genre_id == genre_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100) # limit 100 to avoid too many tracks
            .options(load_only(Track.id, Track.title))
        )
        tracks = result.scalars().all()
        return tracks
    
    async def _get_playlist_tracks(self, playlist_id: int) -> list[Track]:
        '''get playlist tracks'''
        result = await self.db.execute(
            select(Track)
            .join(PlaylistTrack, Track.id == PlaylistTrack.track_id)
            .where(PlaylistTrack.playlist_id == playlist_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100) # limit 100 to avoid too many tracks
            .options(load_only(Track.id, Track.title))
        )
        tracks = result.scalars().all()
        return tracks
    
    async def _get_folder_tracks(self, folder_id: int) -> list[Track]:
        '''get folder tracks'''
        result = await self.db.execute(
            select(Track)
            .where(Track.folder_id == folder_id, Track.is_deleted == False)
            .order_by(Track.updated_at.desc())
            .limit(100)
            .options(load_only(Track.id, Track.title))
        )
        tracks = result.scalars().all()
        return tracks
    
    async def get_collection_tracks(self, collection_type: str, collection_id: int) -> list[Track]:
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
        
    async def get_lyric(self, track_id: int) -> str | None:
        result = await self.db.execute(
            select(Track)
            .options(
                load_only(Track.title, Track.path),
                selectinload(Track.artists).load_only(Artist.name),
            )
            .where(Track.id == track_id)
        )
        track = result.scalar_one_or_none()
        if not track: return None
        
        # first lookup the lyric file with the same name as the track in the track directory
        track_path = (self.settings.MUSIC_LIBRARY_PATH / track.path).resolve()
        lyric_path = track_path.with_suffix('.lrc')
        if lyric_path.exists(): 
            async with aiofiles.open(lyric_path, mode='r', encoding='utf-8') as f:
                return await f.read()
        else:
            # then request the lyric from the lyric server
            params = {'title': track.title, 'artist': track.artists[0].name}
            try:
                res = requests.get(
                    self.settings.LYRIC_OUT_BASE_URL + 'single', 
                    params=params,
                    headers={
                        'Content-Type': 'text/plain',
                        'Authorization': self.config.LYRIC_OUT_API_KEY,
                    },
                    timeout=10
                )
                text = res.text
                # save the lyric file to the track directory with the same name as the track
                if text:
                    async with aiofiles.open(lyric_path, mode='w', encoding='utf-8') as f:
                        await f.write(text)
                    return text
                else:
                    return None
            except requests.exceptions.RequestException as err: 
                logger.error(f'get lyric error: {str(err)}')
                return None
            except IOError:
                logger.error(f'save lyric file error: {lyric_path}')
                return None
            except Exception as e:
                logger.error(f'get lyric error: {e}')
                return None
            
    async def delete_lyric(self, track_id: int) -> None:
        track = await self.db.get(Track, track_id)
        if not track: return
        lyric_path = (self.settings.MUSIC_LIBRARY_PATH / track.path).with_suffix('.lrc')
        try:
            if lyric_path.exists(): 
                lyric_path.unlink()
        except Exception as e:
            logger.error(f'delet lyric {lyric_path} error: {e}')
            raise HTTPException(status_code=500, detail='delete lyric error')

    async def get_tracks_hit_time(self) -> list[datetime]:
        result = await self.db.execute(
            select(TrackHit.played_at)
        )
        return [dt for dt, in result.all()]

    # endregion frontend use