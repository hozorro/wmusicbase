# -*- encoding: utf-8 -*-
'''
@File      :   playlist_service.py
@Time      :   2025/11/29 22:15:26
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   playlist service
'''


import json
from pathlib import Path
from datetime import datetime
from typing import Literal
from fastapi import Request, UploadFile, status
from sqlalchemy import select, update, delete, insert, func, desc
from sqlalchemy.orm import selectinload, joinedload, load_only
from sqlalchemy.exc import IntegrityError
from app.core.deps import SettingsDep, DbDep
from app.core.exceptions import BusinessException
from app.core.logger import logger
from app.models import Track, Artist, Album, Playlist, PlaylistTrack, PlaylistHit, TrackHit, TrackFav, ArtistFav, ArtistHit, User
from app.schemas.playback import PlaylistImportRoot, HitImportRoot, FavImportRoot

class PlaylistService:
    def __init__(self, db: DbDep, settings: SettingsDep, request: Request):
        self.db = db
        self.settings = settings
        self.current_user_id = request.state.user_id

    # region common use
    async def _get_tracks_by_paths(self, paths: list[str]) -> tuple[list[Track], list[Track]]:
        '''lookup tracks according to the paths(ensure the paths exist)'''
        unique_paths = list({path.strip() for path in paths})

        result = await self.db.execute(
            select(Track)
            .where(
                Track.path.in_(unique_paths),
                Track.is_deleted == False
            )
        )
        tracks = result.scalars().all()

        found_paths = {track.path for track in tracks}
        missing_paths = [path for path in unique_paths if path not in found_paths]
        ### if missing_paths exists, return missing info to front, but not affect the creation of playlist.
        ### if stop the playlist creation, raise an exception here.
        ### if missing_paths:
        #     raise Exception(f"some of the track path not exist in db：{', '.join(missing_paths)}")
        # sort tracks according to the sequence in the input(ensure the tracks are in the same order as the input)
        path_to_track = {track.path: track for track in tracks}
        ordered_tracks = [path_to_track[path] for path in paths if path in path_to_track] 
        return ordered_tracks, missing_paths
    
    async def create_playlist_and_bind_tracks(self, title: str, comment: str | None, tracks: list[int] | None = None) -> dict:
        '''create playlist, and bind tracks if needed'''
        tracks = tracks or []
        try:
            # 1. create playlist
            playlist = Playlist(
                title=title,
                comment=comment.strip() if comment else None,
                user_id=self.current_user_id,
            )
            self.db.add(playlist)
            await self.db.flush()

            # 2. bind tracks
            missing = []
            tracks_set = set(tracks)
            if tracks:
                if isinstance(tracks[0], str):  # path
                    valid_tracks, missing = await self._get_tracks_by_paths(tracks_set)
                    playlist_tracks = [
                        PlaylistTrack(
                            playlist_id=playlist.id,
                            track_id=track.id,
                            position=index
                        )
                        for index, track in enumerate(valid_tracks)
                    ]
                else:
                    playlist_tracks = [
                        PlaylistTrack(
                            playlist_id=playlist.id,
                            track_id=id,
                            position=index
                        )
                        for index, id in enumerate(tracks_set)
                    ]
                self.db.add_all(playlist_tracks)

            await self.db.commit()
            await self.db.refresh(playlist)
            logger.info(f"playlist successfully created: ID={playlist.id}, title={playlist.title}, track count={len(tracks)}")
            
            if missing:
                msg = f"partially success: title={playlist.title}, track count={len(tracks)}, some track not exist in db or be deleted: {', '.join(missing)}"
                return {
                    'result': 'partial success',
                    'playlist': playlist,
                    'track_added_count': len(tracks),
                    'detail': msg
                }
            msg = f"successfully created: title={playlist.title}, track count={len(tracks)}"
            return {
                'result': 'success',
                'playlist': playlist,
                'track_added_count': len(tracks),
                'detail': msg
            }
        except IntegrityError as e:
            await self.db.rollback()
            raise BusinessException(
                code=30501, 
                msg=f"fail to create playlist with integrity error: {playlist.title}", 
                status_code=status.HTTP_409_CONFLICT
            )
        except Exception as e:
            await self.db.rollback()
            logger.error(f"fail to create playlist: {e}")
            raise BusinessException(
                code=30502, 
                msg=f"fail to create playlist with unknown error: {playlist.title}", 
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # endregion common use

    # region backend use
    async def parse_playlist_json_file(self, file_path: Path) -> dict:
        playlist = json.loads(file_path.read_text(encoding='utf-8'))
        playlist.update({'filename': file_path.name})
        return playlist
    
    async def get_user_playlists_info(self, all_user: bool = False) -> list[dict]:
        '''get user playlists, only for backend show'''
        playlists = []
        stmt = select(Playlist)
        if not all_user:
            stmt = stmt.where(Playlist.user_id == self.current_user_id, Playlist.is_deleted == False)
        stmt = stmt.order_by(Playlist.created_at.desc()).options(
            joinedload(Playlist.user).load_only(User.username),
            selectinload(Playlist.tracks).options(
                load_only(Track.title),
                selectinload(Track.artists).load_only(Artist.name)
            )
        ).limit(200)    # limited to 200, avoid too many data returned, paginated later...
        result = await self.db.execute(stmt)
        playlist_list = result.scalars().all()
        
        if not playlist_list:
            return playlists
        
        # batch query track position info of all playlists
        playlist_ids = [p.id for p in playlist_list]
        pos_result = await self.db.execute(
            select(PlaylistTrack.playlist_id, PlaylistTrack.track_id, PlaylistTrack.position)
            .where(PlaylistTrack.playlist_id.in_(playlist_ids))
        )
        
        # build position map: {playlist_id: {track_id: position}}
        pos_map = {}
        for row in pos_result:
            if row.playlist_id not in pos_map:
                pos_map[row.playlist_id] = {}
            pos_map[row.playlist_id][row.track_id] = row.position
        
        for playlist in playlist_list:
            # sort tracks by position
            track_pos_map = pos_map.get(playlist.id, {})
            sorted_tracks = sorted(playlist.tracks, key=lambda t: track_pos_map.get(t.id, 0))
            
            playlists.append({
                'id': playlist.id,
                'title': playlist.title,
                'username': playlist.user.username,
                'tracks': [{'title': track.title, 'artists': [a.name for a in track.artists]} for track in sorted_tracks]
            })
        return playlists

    async def get_user_playlist_data(self, user_id: int) -> dict:
        '''get user playlist data, only for backend export, tracks show as path'''
        user = await self.db.get(User, user_id)
        result = await self.db.execute(
            select(Playlist)
            .where(Playlist.user_id == user_id, Playlist.is_deleted == False)
            .options(
                load_only(Playlist.id, Playlist.title, Playlist.comment),
                selectinload(Playlist.user).load_only(User.id, User.username),
                selectinload(Playlist.tracks).load_only(Track.title, Track.path)
            )
        )
        playlists = result.scalars().all()
        return {
            'user': {'id': user.id, 'username': user.username},
            'playlists': [{
                'id': playlist.id,
                'title': playlist.title,
                'comment': playlist.comment,
                'tracks': [track.path for track in playlist.tracks]
            } for playlist in playlists]
        }

    async def get_playlist_data(self, playlist_id: int) -> dict:
        '''get playlist data, only for backend export, tracks show as path'''
        result = await self.db.execute(
            select(Playlist)
            .where(Playlist.id == playlist_id)
            .options(
                load_only(Playlist.id, Playlist.title, Playlist.comment),
                joinedload(Playlist.user).load_only(User.id, User.username),
                joinedload(Playlist.tracks).load_only(Track.title, Track.path)
            )
        )
        playlist = result.scalars().first()
        if playlist:
            return {
                'id': playlist.id,
                'title': playlist.title,
                'comment': playlist.comment,
                'user': {'id': playlist.user.id, 'username': playlist.user.username},
                'tracks': [{'title': track.title, 'path': track.path} for track in playlist.tracks]
            }
    
    async def create_playlist_from_json(self, filename: str) -> str:
        '''create playlist from json file'''
        playlist = await self.parse_playlist_json_file(self.settings.PLAYLISTS_TMP_DIR / filename)
        return await self.create_playlist_and_bind_tracks(
            playlist.get('title'),
            playlist.get('comment'),
            tracks=playlist.get('tracks')
        )
    # endregion backend use

    # region frontend use
    async def get_top_playlists(self, limit: int = 6) -> list[dict]:
        '''get the most played playlists'''
        track_count_subq = (
            select(
                PlaylistTrack.playlist_id,
                func.count(PlaylistTrack.track_id).label('track_count')
            )
            .group_by(PlaylistTrack.playlist_id)
            .subquery()
        )
        stmt = (
            select(
                Playlist.id,
                Playlist.title,
                Playlist.cover_art_hash,
                func.count(PlaylistHit.id).label('hit_count'),
                func.coalesce(track_count_subq.c.track_count, 0).label('track_count')
            )
            .outerjoin(PlaylistHit, PlaylistHit.playlist_id == Playlist.id)
            .outerjoin(track_count_subq, Playlist.id == track_count_subq.c.playlist_id)
            .where(Playlist.user_id == self.current_user_id, Playlist.is_deleted == False)
            .group_by(Playlist.id, track_count_subq.c.track_count)
            .order_by(desc('hit_count'), Playlist.updated_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        playlists = [
            {'id': id, 'title': title, 'cover_art_hash': cover_art_hash, 'track_count': track_count}
            for id, title, cover_art_hash, _, track_count in result.all()
        ]
        return playlists
    
    async def get_user_playlists(self) -> list[dict]:
        '''get user playlists with track count'''
        track_count_subq = (
            select(
                PlaylistTrack.playlist_id,
                func.count(PlaylistTrack.track_id).label('track_count')
            )
            .group_by(PlaylistTrack.playlist_id)
            .subquery()
        )
        stmt = (
            select(
                Playlist,
                func.coalesce(track_count_subq.c.track_count, 0).label('track_count')
            )
            .outerjoin(track_count_subq, Playlist.id == track_count_subq.c.playlist_id)
            .where(Playlist.user_id == self.current_user_id, Playlist.is_deleted == False)
            .order_by(Playlist.updated_at.desc())
        )
        result = await self.db.execute(stmt)
        playlists = []
        for row in result:
            playlist = row[0]
            playlist.track_count = row.track_count
            playlists.append(playlist)
        return playlists
    
    async def get_playlist_info(self, playlist_id: int) -> Playlist | None:
        '''get playlist info with track positions'''
        stmt = (
            select(Playlist)
            .where(Playlist.id == playlist_id)
            .options(
                joinedload(Playlist.user).load_only(User.username),
                selectinload(Playlist.tracks)
                .options(
                    load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                    joinedload(Track.album).load_only(Album.id, Album.title),
                    selectinload(Track.artists).load_only(Artist.id, Artist.name)
                )
            )
        )
        result = await self.db.execute(stmt)
        playlist = result.scalar_one_or_none()
        if playlist is None: 
            return None

        # attach position from PlaylistTrack to each track
        pos_result = await self.db.execute(
            select(PlaylistTrack.track_id, PlaylistTrack.position)
            .where(PlaylistTrack.playlist_id == playlist_id)
        )
        pos_map = {row.track_id: row.position for row in pos_result}
        for track in playlist.tracks:
            track.position = pos_map.get(track.id, 0)

        return playlist
    
    async def update_playlist(
        self, 
        playlist_id: int, 
        title: str | None = None,
        comment: str | None = None,
    ) -> Playlist | None:
        '''update playlist info'''
        playlist = await self.db.get(Playlist, playlist_id)
        if playlist is None or playlist.user_id != self.current_user_id or title is None:
            return None
        playlist.title = title
        if comment is not None:
            playlist.comment = comment.strip()
        self.db.add(playlist)
        await self.db.commit()
        await self.db.refresh(playlist)
        return playlist
    
    async def delete_playlist(self, playlist_id: int) -> None:
        '''soft delete playlist (mark is_deleted)'''
        playlist = await self.db.get(Playlist, playlist_id)
        if playlist is None or playlist.user_id != self.current_user_id:
            raise BusinessException(
                code=30503, 
                msg=f'playlist not found when delete: {playlist_id}', 
                status_code=status.HTTP_404_NOT_FOUND
            )
        playlist.is_deleted = True
        self.db.add(playlist)
        await self.db.commit()
    
    async def add_track_to_playlist(self, playlist_id: int, track_id: int) -> bool:
        '''add track to playlist, return False if track already exists in playlist'''
        # check if track already exists in playlist
        existing = await self.db.execute(
            select(PlaylistTrack)
            .where(
                PlaylistTrack.playlist_id == playlist_id,
                PlaylistTrack.track_id == track_id
            )
        )
        if existing.scalar_one_or_none() is not None:
            return False
        
        max_pos_subq = (
            select(func.coalesce(func.max(PlaylistTrack.position), -1))
            .where(PlaylistTrack.playlist_id == playlist_id)
            .scalar_subquery()
        )
        await self.db.execute(
            insert(PlaylistTrack)
            .values(
                playlist_id=playlist_id,
                track_id=track_id,
                position=max_pos_subq + 1
            )
        )
        await self.db.commit()
        return True
    
    async def remove_track_from_playlist(self, playlist_id: int, track_id: int) -> Playlist | None:
        '''remove track from playlist'''
        # playlist = await self.db.get(Playlist, playlist_id)
        # if playlist is None or playlist.user_id != self.current_user_id:
        #     return None
        # track = await self.db.get(Track, track_id)
        # if track is None or track.is_deleted:
        #     return None
        await self.db.execute(
            delete(PlaylistTrack)
            .where(
                PlaylistTrack.playlist_id == playlist_id,
                PlaylistTrack.track_id == track_id
            )
        )
        result = await self.db.execute(
            select(PlaylistTrack)
            .where(PlaylistTrack.playlist_id == playlist_id)
            .order_by(PlaylistTrack.position)
        )
        rows = result.scalars().all()

        for new_pos, row in enumerate(rows):
            if row.position != new_pos:
                await self.db.execute(
                    update(PlaylistTrack)
                    .where(
                        PlaylistTrack.playlist_id == playlist_id,
                        PlaylistTrack.track_id == row.track_id
                    )
                    .values(position=new_pos)
                )
        await self.db.commit()

    async def move_playlist_track(self, playlist_id: int, track_id: int, new_position: int) -> None:
        '''move track to target position in playlist'''
        result = await self.db.execute(
            select(PlaylistTrack.track_id)
            .where(PlaylistTrack.playlist_id == playlist_id)
            .order_by(PlaylistTrack.position)
        )
        track_ids = [row[0] for row in result.all()]

        if track_id not in track_ids:
            raise BusinessException(
                code=30505, 
                msg=f'track not found in playlist when move: {track_id}', 
                status_code=status.HTTP_404_NOT_FOUND
            )
        if new_position < 0 or new_position >= len(track_ids):
            raise BusinessException(
                code=30506, 
                msg=f'invalid position when move track in playlist: {track_id}-{new_position}', 
                status_code=status.HTTP_400_BAD_REQUEST
            )

        track_ids.remove(track_id)
        track_ids.insert(new_position, track_id)

        for new_pos, tid in enumerate(track_ids):
            await self.db.execute(
                update(PlaylistTrack)
                .where(
                    PlaylistTrack.playlist_id == playlist_id,
                    PlaylistTrack.track_id == tid
                )
                .values(position=new_pos)
            )
        await self.db.commit()

    # endregion frontend use

class PlayBackService:
    def __init__(self, db: DbDep, request: Request):
        self.db = db
        self.current_user_id = request.state.user_id

    # region hit & fav
    async def add_track_hit(self, track_id: int):
        '''record a track play hit'''
        hit = TrackHit(track_id=track_id, user_id=self.current_user_id)
        self.db.add(hit)
        await self.db.commit()

    async def get_track_hits(self, track_id: int) -> list[datetime]:
        '''get all play hit times of track for current user, oldest first'''
        result = await self.db.execute(
            select(TrackHit.played_at)
            .where(TrackHit.track_id == track_id, TrackHit.user_id == self.current_user_id)
            .order_by(TrackHit.played_at.asc())
        )
        return [row[0] for row in result.all()]

    async def add_artist_hit(self, artist_id: int):
        '''record an artist play hit'''
        hit = ArtistHit(artist_id=artist_id, user_id=self.current_user_id)
        self.db.add(hit)
        await self.db.commit()

    async def add_playlist_hit(self, playlist_id: int):
        '''record a playlist play hit'''
        hit = PlaylistHit(playlist_id=playlist_id, user_id=self.current_user_id)
        self.db.add(hit)
        await self.db.commit()

    async def favorite_track(self, track_id: int, is_favorited: bool) -> datetime | None:
        '''favorite or unfavorite a track'''
        favorited_at = None
        if is_favorited:
            existing_fav = await self.db.execute(
                select(TrackFav).where(TrackFav.user_id == self.current_user_id, TrackFav.track_id == track_id)
            )
            if existing_fav.scalar_one_or_none():
                return None  # already favorited
            new_fav = TrackFav(user_id=self.current_user_id, track_id=track_id)
            self.db.add(new_fav)
            await self.db.flush()
            favorited_at = new_fav.favorited_at
        else:
            await self.db.execute(
                delete(TrackFav).where(TrackFav.user_id == self.current_user_id, TrackFav.track_id == track_id)
            )
        await self.db.commit()
        return favorited_at

    async def favorite_artist(self, artist_id: int, is_favorited: bool) -> datetime | None:
        '''favorite or unfavorite an artist'''
        favorited_at = None
        if is_favorited:
            existing_fav = await self.db.execute(
                select(ArtistFav).where(ArtistFav.user_id == self.current_user_id, ArtistFav.artist_id == artist_id)
            )
            if existing_fav.scalar_one_or_none():
                return None  # already favorited
            new_fav = ArtistFav(user_id=self.current_user_id, artist_id=artist_id)
            self.db.add(new_fav)
            await self.db.flush()
            favorited_at = new_fav.favorited_at
        else:
            await self.db.execute(
                delete(ArtistFav).where(ArtistFav.user_id == self.current_user_id, ArtistFav.artist_id == artist_id)
            )
        await self.db.commit()
        return favorited_at

    # endregion hit & fav

class PlayDataService:
    def __init__(self, db: DbDep):
        self.db = db

    async def validate_upload_file(self, file: UploadFile, category: Literal['playlists', 'hits', 'favorites']) -> list:
        # 1. validate upload file
        if file.content_type not in ['application/json', 'text/json']:
            raise BusinessException(
                code=70601, 
                msg='upload playdata backup file type error', 
                detail={'allowed_types': ['application/json', 'text/json']},
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            )
        
        # 2. limit file size（5MB）
        file_size = file.read(1)
        await file.seek(0)
        if file_size > 5 * 1024 * 1024:  # 5MB
            raise BusinessException(
                code=70602, 
                msg='upload playdata backup file size exceed', 
                detail={'limit': '5MB'},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE
            )
        
        # 3. read and parse json file
        try:
            file_content = await file.read()
            json_data = json.loads(file_content.decode('utf-8'))
        except UnicodeDecodeError:  # decode error
            raise BusinessException(
                code=70603, 
                msg='upload playdata backup file decode error', 
                detail={'allowed_encoding': 'UTF-8'},
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
            )
        except json.JSONDecodeError as e:  # json parse error
            raise BusinessException(
                code=70604, 
                msg='playdata backup file parse error', 
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
            )
        finally:
            await file.close()

        # 4. validate json structure
        if category not in json_data or not isinstance(json_data[category], list):
            raise BusinessException(
                code=70605, 
                msg='playdata backup file json structure error', 
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
            )
        
        return json_data[category]
        
    async def get_user_track_hits_data(self, user_id: int) -> dict:
        user = await self.db.get(User, user_id)
        stmt = select(TrackHit).options(
            joinedload(TrackHit.track).load_only(Track.path)
        ).where(TrackHit.user_id == user_id).order_by(TrackHit.played_at.asc())
        result = await self.db.execute(stmt)
        return {
            'user': {'id': user.id, 'username': user.username}, 
            'hits': [{
                'track': hit.track.path,
                'played_at': hit.played_at.isoformat()
            } for hit in result.scalars().all()]
        }
    
    async def get_user_track_favorites_data(self, user_id: int) -> dict:
        user = await self.db.get(User, user_id)
        stmt = select(TrackFav).options(
            joinedload(TrackFav.track).load_only(Track.title, Track.path)
        ).where(TrackFav.user_id == user_id).order_by(TrackFav.favorited_at.asc())
        result = await self.db.execute(stmt)
        return {
            'user': {'id': user.id, 'username': user.username},
            'favorites': [{
                'track': fav.track.path,
                'favorited_at': fav.favorited_at.isoformat()
            } for fav in result.scalars().all()]
        }

    async def import_playlist_from_json(self, user_id: int, json_data: list, mode: Literal['merge', 'replace', 'skip']) -> dict:
        '''restore user playlist from json file'''
        # 1. verify json structure
        try:
            import_schema = PlaylistImportRoot(json_data)
            import_playlists_data = import_schema.root
        except Exception as e:
            raise BusinessException(
                code=70502, 
                msg='import playlist from json error', 
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
            )
        
        # 2. init stats
        stats = {
            'total': len(import_playlists_data),
            'success': 0,
            'skipped': 0,
            'failed': 0,
            'errors': []
        }

        # 3. lookup depended data(in batches to reduce db interaction)
        # 3.1 lookup tracks by path(tracks in json are path strings)
        track_paths = {path for p in import_playlists_data for path in (p.tracks or [])}
        track_result = await self.db.execute(
            select(Track)
            .where(Track.path.in_(track_paths))
        )
        tracks = {track.path: track for track in track_result.scalars().all()}

        # 3.2 lookup existing playlists of the user by title
        # playlist id is the primary key, title may be duplicated,
        # so group by title and only keep the first one(lowest id) for each title
        playlist_titles = {p.title for p in import_playlists_data}
        playlist_result = await self.db.execute(
            select(Playlist)
            .where(
                Playlist.user_id == user_id,
                Playlist.is_deleted == False,
                Playlist.title.in_(playlist_titles)
            )
            .order_by(Playlist.id.asc())
        )
        existing_playlists: dict[str, Playlist] = {}
        for existing in playlist_result.scalars().all():
            if existing.title not in existing_playlists:
                existing_playlists[existing.title] = existing

        # 3.3 for merge mode, batch preload existing track ids and max position of matched playlists
        # to avoid querying db in the loop(N+1)
        existing_track_ids_map: dict[int, set[int]] = {}
        max_position_map: dict[int, int] = {}
        if mode == 'merge' and existing_playlists:
            playlist_ids = [p.id for p in existing_playlists.values()]
            pt_result = await self.db.execute(
                select(PlaylistTrack.playlist_id, PlaylistTrack.track_id, PlaylistTrack.position)
                .where(PlaylistTrack.playlist_id.in_(playlist_ids))
            )
            for playlist_id, track_id, position in pt_result.all():
                existing_track_ids_map.setdefault(playlist_id, set()).add(track_id)
                max_position_map[playlist_id] = max(max_position_map.get(playlist_id, -1), position)

        # 4. handle each playlist
        for idx, playlist_data in enumerate(import_playlists_data):
            try:
                playlist = existing_playlists.get(playlist_data.title)

                # 4.1 playlist with the same title exists, handle according to mode
                if playlist is not None:
                    if mode == 'skip':
                        stats['errors'].append(f'Index {idx}: Playlist {playlist_data.title} already exists, skipped')
                        stats['skipped'] += 1
                        continue

                    # update playlist info
                    playlist.title = playlist_data.title
                    playlist.comment = playlist_data.comment
                    self.db.add(playlist)

                    if mode == 'replace':
                        # clear the tracks of the current playlist, then bind imported tracks
                        await self.db.execute(
                            delete(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist.id)
                        )
                        stats['errors'].append(f'Index {idx}: Playlist {playlist_data.title} already exists, replaced')
                else:
                    # 4.2 no playlist with the same title, create a new one
                    playlist = Playlist(
                        title=playlist_data.title,
                        comment=playlist_data.comment,
                        user_id=user_id
                    )
                    self.db.add(playlist)
                    await self.db.flush()

                # 4.3 handle binded tracks(many to many)
                # for merge mode, deduplicate with preloaded existing track ids
                existing_track_ids = existing_track_ids_map.get(playlist.id, set()) if mode == 'merge' else set()

                track_ids = []
                for path in playlist_data.tracks or []:
                    track = tracks.get(path)
                    if track is None:
                        stats['errors'].append(f'Index {idx}: Track {path} not found, skipped')
                        continue
                    if mode == 'merge' and track.id in existing_track_ids:
                        stats['errors'].append(f'Index {idx}: duplicated and skip: {path}')
                        continue
                    track_ids.append(track.id)
                    existing_track_ids.add(track.id)

                # bind tracks in batches
                if track_ids:
                    if mode == 'merge':
                        # append after existing tracks, position continues from preloaded max position
                        position = max_position_map.get(playlist.id, -1) + 1
                    else:
                        # create or replace mode, position starts from 0
                        position = 0
                    association_data = [
                        {'playlist_id': playlist.id, 'track_id': track_id, 'position': pos}
                        for pos, track_id in enumerate(track_ids, start=position)
                    ]
                    await self.db.execute(
                        insert(PlaylistTrack).values(association_data)
                    )
                # commit each playlist independently, so a single failure does not affect others
                await self.db.commit()
                stats['success'] += 1
            except Exception as e:
                # rollback to recover session state, so the failure of a single playlist
                # does not affect the import of the remaining playlists
                await self.db.rollback()
                stats['failed'] += 1
                stats['errors'].append(f'Index {idx}: Failed to import - {str(e)}')

        return stats
    
    async def import_hit_from_json(self, user_id: int, json_data: list) -> dict:
        """restore user hits from json file"""
        try:
            import_schema = HitImportRoot(json_data)
            import_hits_data = import_schema.root
        except Exception as e:
            raise BusinessException(
                code=70606, 
                msg='import hit from json error', 
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
            )
        
        stats = {
            'total': len(import_hits_data),
            'success': 0,
            'failed': 0,
            'errors': []
        }

        track_paths = {hit.track for hit in import_hits_data}
        track_result = await self.db.execute(
            select(Track)
            .where(Track.path.in_(track_paths))
        )
        tracks = {track.path: track for track in track_result.scalars().all()}

        # clear the hits of the current user
        await self.db.execute(
            delete(TrackHit).where(TrackHit.user_id == user_id)
        )

        insert_data = []
        for hit_data in import_hits_data:
            track = tracks.get(hit_data.track)
            if track: 
                insert_data.append({
                    'played_at': hit_data.played_at,
                    'track_id': track.id,
                    'user_id': user_id
                })
                stats['success'] += 1
            else: 
                stats['errors'].append(f'Track {hit_data.track} not found, skipped')
                stats['failed'] += 1
        if insert_data:
            try:
                await self.db.execute(
                    insert(TrackHit).values(insert_data)
                )
            except Exception as e:
                stats['errors'] = [f'Failed to import: error when insert to db.']
                stats['failed'] = 1
        return stats

    async def import_fav_from_json(self, user_id: int, json_data: dict) -> dict:
        """restore user favs from json file"""
        try:
            import_schema = FavImportRoot(json_data)
            import_favs_data = import_schema.root
        except Exception as e:
            raise BusinessException(
                code=70607, 
                msg='import favorite from json error', 
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
            )
        
        stats = {
            'total': len(import_favs_data),
            'success': 0,
            'failed': 0,
            'errors': []
        }

        track_paths = {fav.track for fav in import_favs_data}
        track_result = await self.db.execute(
            select(Track)
            .where(Track.path.in_(track_paths))
        )
        tracks = {track.path: track for track in track_result.scalars().all()}

        # clear the favs of the current user
        await self.db.execute(
            delete(TrackFav).where(TrackFav.user_id == user_id)
        )

        insert_data = []
        for fav in import_favs_data:
            track = tracks.get(fav.track)
            if track: 
                insert_data.append({
                    'favorited_at': fav.favorited_at,
                    'track_id': track.id,
                    'user_id': user_id
                })
                stats['success'] += 1
            else: 
                stats['errors'].append(f'Track {fav.track} not found, skipped')
                stats['failed'] += 1
        if insert_data:
            try: 
                await self.db.execute(
                    insert(TrackFav).values(insert_data)
                )
            except Exception:
                stats['errors'] = [f'Failed to import: error when insert to db.']
                stats['failed'] = 1
        return stats
