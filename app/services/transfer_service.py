# -*- encoding: utf-8 -*-
'''
@File      :   transfer_service.py
@Time      :   2025/12/09 17:00:26
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   transfer service
'''


from datetime import datetime, timezone
from fastapi import Request, HTTPException
from sqlalchemy import select, delete, insert, func, or_, distinct
from sqlalchemy.orm import selectinload, load_only
from app.core.deps import DbDep, SettingsDep
from app.schemas.transfer import TransferHitsList, TransferFav, UploadPlaylists
from app.models import (
    Album, Artist, ArtistFav, Folder, Genre, Playlist, track_artists,
    PlaylistHit, PlaylistTrack, SyncMeta, Track, TrackFav, TrackHit
)
from app.services.sync import Syncer

class TransferService:
    def __init__(self, db: DbDep, settings: SettingsDep, request: Request):
        self.db = db
        self.settings = settings
        self.current_user_id = request.state.user_id
        self.models = {
            'track': Track,
            'album': Album,
            'artist': Artist,
            'folder': Folder,
            'genre': Genre,
            'trackhit': TrackHit,
            'trackfav': TrackFav,
            'artistfav': ArtistFav,
            'playlisthit': PlaylistHit,
            'playlist': Playlist
        }

    async def get_db_music_meta(self) -> dict[str, int | datetime]:
        '''
        Get the basic music meta data.
        The basic music includes tracks, albums, artists, folders, genres,
        whose meta data change only in the server side.
        '''
        result = await self.db.execute(
            select(SyncMeta)
            .where(or_(SyncMeta.user_id == self.current_user_id, SyncMeta.user_id == None))
        )
        music_meta = result.scalars().all()
        return music_meta
    
    async def get_user_playback_meta(self):
        '''
        Get user playback meta data, includes track hits, track favorites, artist favorites, playlist hits.
        These meta data change or be uploaded only from the client side with multiple clients(devices).
        So the value of count and last_update is of no sense.
        '''
        pass
    
    async def get_unsync_count(self, model_name: str, last_sync: datetime | None) -> int:
        '''Get the number of unsync count of music entity, including the soft deleted tracks.'''
        model = self.models[model_name]
        last_sync = last_sync or datetime.min.replace(tzinfo=timezone.utc)
        unsync_count = await self.db.scalar(
            select(func.count(model.id)).where(model.updated_at > last_sync)
        )
        return unsync_count
        
    async def transfer_albums(self, last_sync: datetime, page_num: int = 1, page_size: int = 100) -> list[Album]:
        result = await self.db.execute(
            select(Album).options(
                selectinload(Album.album_artist).load_only(Artist.id, Artist.name),
                selectinload(Album.tracks).options(
                    load_only(Track.id),
                    selectinload(Track.artists).load_only(Artist.id, Artist.name),
                )
            )
            .where(Album.updated_at > last_sync)
            .order_by(Album.created_at).offset((page_num - 1) * page_size).limit(page_size)
        )
        albums = result.scalars().all()
        return albums
    
    async def transfer_artists(self, last_sync: datetime, page_num: int = 1, page_size: int = 100) -> list[dict]:
        stmt = (
            select(
                Artist.id, 
                Artist.name, 
                Artist.pinyin_initial, 
                Artist.face_art_hash,
                Artist.portrait_art_hash,
                func.count(Track.id).label('track_count'), 
            ).select_from(Artist)
            .outerjoin(track_artists, Artist.id == track_artists.c.artist_id)
            .outerjoin(Track, Track.id == track_artists.c.track_id)
            .where(Artist.updated_at > last_sync)
            .group_by(Artist.id)
            .order_by(Artist.created_at).offset((page_num - 1) * page_size).limit(page_size)
        )
        result = await self.db.execute(stmt)
        artists = [{
            'id': id,
            'name': name,
            'pinyin_initial': pinyin_initial,
            'face_art_hash': face_art_hash,
            'portrait_art_hash': portrait_art_hash,
            'track_count': track_count,
        } for (id, name, pinyin_initial, face_art_hash, portrait_art_hash, track_count) in result.all()]
        return artists

    async def transfer_folders(self, last_sync: datetime, page_num: int = 1, page_size: int = 100, ) -> list[Folder]:
        result = await self.db.execute(
            select(Folder)
            .where(Folder.updated_at > last_sync)
            .order_by(Folder.created_at).offset((page_num - 1) * page_size).limit(page_size)
        )
        folders = result.scalars().all()
        return folders
    
    async def transfer_genres(self, last_sync: datetime, page_num: int = 1, page_size: int = 100) -> list[Genre]:
        result = await self.db.execute(
            select(Genre).where(Genre.updated_at > last_sync)
            .order_by(Genre.created_at).offset((page_num - 1) * page_size).limit(page_size)
        )
        genres = result.scalars().all()
        return genres
    
    async def transfer_tracks(self, last_sync: datetime, page_num: int = 1, page_size: int = 100) -> list[Track]:
        '''Get track records whose updated_at is greater than last_sync.
        The is_deleted field should not be filtered out, because it is used to determine whether to delete the track
        in the front end.
        '''
        track_stmt = (
            select(Track)
            .where(
                # Track.is_deleted == False, 
                Track.updated_at > last_sync
            )
            .options(
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                selectinload(Track.genres).load_only(Genre.id),
                selectinload(Track.album).load_only(Album.id, Album.title)
            )
            .order_by(Track.created_at).offset((page_num - 1) * page_size).limit(page_size)
        )
        result = await self.db.execute(track_stmt)
        tracks = result.scalars().all()
        return tracks

# When prune track records, delete tracks whose updated_at is **less than** last_sync,
# or the front end can not know whether the track is deleted or not.
# But this is still not effective when the front end is from multiple devices, because the last_sync is different on each device.
# A probably solution is to add a new field to mark the device uuid, and prune track records whose updated_at is less than the **min last_sync** of all devices.
# Then if the last_sync of some device is not synced for a long time, the front end can notify the user to sync the data,
# or theses devices last_sync records should be deleted after a certain period of time, because the devices can be thinked to be not used anymore.
    async def get_track_hits_records_count(self) -> int:
        count = await self.db.scalar(
            select(func.count(distinct(TrackHit.track_id)))
            .join(Track, Track.id == TrackHit.track_id)
            .where(
                TrackHit.user_id == self.current_user_id,
                Track.is_deleted == False
            )
        ) or 0
        return count
    async def get_artist_hits_records_count(self) -> int:
        count = await self.db.scalar(
            select(func.count(distinct(Artist.id)))
            .select_from(Artist)
            .join(track_artists, track_artists.c.artist_id == Artist.id)
            .join(Track, Track.id == track_artists.c.track_id)
            .join(TrackHit, Track.id == TrackHit.track_id)
            .where(
                TrackHit.user_id == self.current_user_id,
                Track.is_deleted == False
            )
        ) or 0
        return count
    async def get_playlist_hits_records_count(self) -> int:
        count = await self.db.scalar(
            select(func.count(distinct(PlaylistHit.playlist_id)))
            .join(Playlist, Playlist.id == PlaylistHit.playlist_id)
            .where(
                PlaylistHit.user_id == self.current_user_id,
                Playlist.is_deleted == False
            )
        ) or 0
        return count
    async def upload_track_hits(self, hits: TransferHitsList) -> int:
        '''Upload track hits to database.
        - hits: list[UploadTrackHit], [{'track_id': 1, 'played_ats': ['2021-01-01 00:00:00', ...]}, ...]
        '''
        # 1. check the hits records existed
        data = set()
        for hit in hits.root:   # should add .root here
            for played_at in hit.played_ats:
                played_at = played_at.replace(tzinfo=timezone.utc) if played_at.tzinfo is None else played_at
                data.add((hit.id, played_at))

        stmt = select(TrackHit.track_id, TrackHit.played_at).where(
            TrackHit.user_id == self.current_user_id,
            TrackHit.track_id.in_([hit.id for hit in hits.root]),
        )
        result = await self.db.execute(stmt)
        for track_id, played_at in result.all():
            data.discard((track_id, played_at))
        data_add = sorted(data, key=lambda x: x[1])

        # 2. insert the new hits records
        new_hits = []
        for track_id, played_at in data_add:
            new_hits.append(TrackHit(track_id=track_id, played_at=played_at, user_id=self.current_user_id))

        if new_hits:
            self.db.add_all(new_hits)
            await self.db.commit()

        syncer = Syncer(self.db, self.settings)
        await syncer.update_playback_sync_meta('trackhit', self.current_user_id)

        return len(new_hits)

    async def download_track_hits(self, page_num: int = 1, page_size: int = 100) -> list[dict]:
        '''Download track hits from database.'''
        hit_subq = (
            select(
                TrackHit.track_id,
                func.array_agg(TrackHit.played_at).label('played_ats')
            ).where(
                TrackHit.user_id == self.current_user_id,
                Track.id == TrackHit.track_id,  # 此处写法是否有错？
                Track.is_deleted == False
            ).group_by(TrackHit.track_id).subquery()
        )
        stmt = (
            select(hit_subq.c.track_id, hit_subq.c.played_ats)
            .join(Track, Track.id == hit_subq.c.track_id)
            .where(
                Track.is_deleted == False
            ).offset((page_num - 1) * page_size).limit(page_size)
        )
        result = await self.db.execute(stmt)
        return [{
            'id': track_id,
            'played_ats': played_ats
        } for track_id, played_ats in result.all()]
    
    async def download_artist_hits(self, page_num: int = 1, page_size: int = 100) -> list[dict]:
        '''Download artist hits from database. created by the track hits and track_artists tables.'''
        stmt = (
            select(Artist.id, func.count(TrackHit.id).label('hit_count'))
            .select_from(Artist)
            .join(track_artists, track_artists.c.artist_id == Artist.id)
            .join(Track, Track.id == track_artists.c.track_id)
            .join(TrackHit, TrackHit.track_id == Track.id)
            .where(
                TrackHit.user_id == self.current_user_id,
                Track.is_deleted == False
            )
            .group_by(Artist.id)
            .order_by(Artist.id)
            .offset((page_num - 1) * page_size).limit(page_size)
        )
        result = await self.db.execute(stmt)
        return [{
            'artist_id': artist_id,
            'hit_count': hit_count
        } for artist_id, hit_count in result.all()]
    
    async def upload_track_favs(self, added: list[TransferFav], removed: list[TransferFav]) -> int:
        '''Upload track favs to database.
        - added: list[UploadTrackFav], [{'track_id': 1, 'favorited_at': '2021-01-01 00:00:00'}, ...]
        - removed: list[UploadTrackFav], [{'track_id': 1, 'favorited_at': '2021-01-01 00:00:00'}, ...]
        '''
        for item in added:
            favorited_at = item.favorited_at.replace(tzinfo=timezone.utc) if item.favorited_at.tzinfo is None else item.favorited_at
            fav = TrackFav(track_id=item.track_id, favorited_at=favorited_at, user_id=self.current_user_id)
            self.db.add(fav)
        
        await self.db.execute(
            delete(TrackFav).where(
                TrackFav.track_id.in_([item.track_id for item in removed]),
                TrackFav.user_id == self.current_user_id
            )
        )

        await self.db.commit()

        syncer = Syncer(self.db, self.settings)
        await syncer.update_playback_sync_meta('trackfav', self.current_user_id)

        return len(added) + len(removed)

    async def download_track_favs(self) -> list[TrackFav]:
        result = await self.db.execute(
            select(TrackFav).where(
                TrackFav.user_id == self.current_user_id
            )
            .order_by(TrackFav.favorited_at)
        )
        return result.scalars().all()

    async def upload_artist_favs(self, added: list[TransferFav], removed: list[TransferFav]) -> int:
        '''Upload artist favs to database.
        - added: list[UploadTrackFav], [{'track_id': 1, 'favorited_at': '2021-01-01 00:00:00'}, ...]
        - removed: list[UploadTrackFav], [{'track_id': 1, 'favorited_at': '2021-01-01 00:00:00'}, ...]
        '''
        for item in added:
            favorited_at = item.favorited_at.replace(tzinfo=timezone.utc) if item.favorited_at.tzinfo is None else item.favorited_at
            fav = ArtistFav(track_id=item.track_id, favorited_at=favorited_at, user_id=self.current_user_id)
            self.db.add(fav)
        
        await self.db.execute(
            delete(ArtistFav).where(
                ArtistFav.track_id.in_([item.track_id for item in removed]),
                ArtistFav.user_id == self.current_user_id
            )
        )

        await self.db.commit()

        syncer = Syncer(self.db, self.settings)
        await syncer.update_playback_sync_meta('artistfav', self.current_user_id)

        return len(added) + len(removed)

    async def download_artist_favs(self) -> list[ArtistFav]:
        result = await self.db.execute(
            select(ArtistFav).where(
                ArtistFav.user_id == self.current_user_id
            )
            .order_by(ArtistFav.favorited_at)
        )
        return result.scalars().all()

    async def upload_playlist_hits(self, hits: TransferHitsList) -> int:
        '''Upload playlist hits to database.
        - hits: list[UploadPlaylistHit], [{'playlist_id': 1, 'played_at': '2021-01-01 00:00:00'}, ...]
        '''
        # 1. check the hits records existed
        existed = set()
        for hit in hits.root:
            for played_at in hit.played_ats:
                played_at = played_at.replace(tzinfo=timezone.utc) if played_at.tzinfo is None else played_at
                existed.add((hit.id, played_at))
        stmt = select(PlaylistHit.playlist_id, PlaylistHit.played_at).where(
            PlaylistHit.user_id == self.current_user_id,
            PlaylistHit.playlist_id.in_([hit.id for hit in hits.root]),
        )
        result = await self.db.execute(stmt)
        for playlist_id, played_at in result.all():
            existed.discard((playlist_id, played_at))
        existed_hits = sorted(existed, key=lambda x: x[1])

        # 2. insert the new hits records
        new_hits = []
        for playlist_id, played_at in existed_hits:
            new_hits.append(PlaylistHit(playlist_id=playlist_id, played_at=played_at, user_id=self.current_user_id))
        
        if new_hits:
            self.db.add_all(new_hits)
            await self.db.commit()

        syncer = Syncer(self.db, self.settings)
        await syncer.update_playback_sync_meta('playlisthit', self.current_user_id)

        return len(new_hits)

    async def download_playlist_hits(self, page_num: int = 1, page_size: int = 100) -> list[dict]:
        hit_subq = (
            select(
                PlaylistHit.playlist_id,
                func.array_agg(PlaylistHit.played_at).label('played_ats')
            ).where(
                PlaylistHit.user_id == self.current_user_id,
                Playlist.id == PlaylistHit.playlist_id,
                Playlist.is_deleted == False
            ).group_by(PlaylistHit.playlist_id).subquery()
        )
        stmt = (
            select(hit_subq.c.playlist_id, hit_subq.c.played_ats)
            .join(PlaylistHit, PlaylistHit.playlist_id == hit_subq.c.playlist_id)
            .where(Playlist.is_deleted == False)
            .offset((page_num - 1) * page_size).limit(page_size)
        )
        result = await self.db.execute(stmt)
        return [{
            'id': playlist_id,
            'played_ats': played_ats
        } for playlist_id, played_ats in result.all()]

    async def upload_playlists(self, playlists: UploadPlaylists) -> dict:
        '''Upload playlists to database.
        - playlists: list[UploadPlaylist], [{ "id", "title", "comment", "is_deleted", "tracks": ["track_id"]}]
        '''
        updated = 0
        created = 0
        for pl_data in playlists.root:
            # 1. update or insert playlists
            comment = pl_data.comment if hasattr(pl_data, 'comment') else ''
            is_deleted = pl_data.is_deleted if hasattr(pl_data, 'is_deleted') else False
            if pl_data.id is not None:
                # update existing playlist
                playlist_id = pl_data.id
                playlist = await self.db.get(Playlist, playlist_id)
                if not playlist or playlist.user_id != self.current_user_id:
                    raise HTTPException(status_code=404, detail='Playlist not found')
                
                playlist.title = pl_data.title
                playlist.comment = comment
                playlist.is_deleted = is_deleted
                updated += 1
            else:   # new playlist with no id
                # insert new playlist
                playlist = Playlist(
                    title=pl_data.title,
                    comment=comment,
                    is_deleted=is_deleted,
                    user_id=self.current_user_id
                )
                self.db.add(playlist)
                await self.db.flush()
                created += 1

            # 2. update or insert playlist tracks(clear old tracks first)
            await self.db.execute(
                delete(PlaylistTrack).where(PlaylistTrack.playlist_id == playlist.id)
            )
            if not is_deleted and hasattr(pl_data, 'track_ids'):
                track_records = [
                    {
                        'playlist_id': playlist.id,
                        'track_id': track_id,
                        'position': pl_data.track_ids.index(track_id),
                    } for track_id in pl_data.track_ids
                ]
                if track_records:
                    await self.db.execute(
                        insert(PlaylistTrack).values(track_records)
                    )
        await self.db.commit()

        syncer = Syncer(self.db, self.settings)
        await syncer.update_playback_sync_meta('playlist', self.current_user_id)

        return {'total': len(playlists.root), 'updated': updated, 'created': created}

    async def download_playlists(self) -> list[Playlist]:
        '''Get all playlists of current user.'''
        result = await self.db.execute(
            select(Playlist).options(
                selectinload(Playlist.tracks).load_only(Track.id),
            )
            .where(Playlist.user_id == self.current_user_id, Playlist.is_deleted == False)
            .order_by(Playlist.created_at)
        )
        playlists = result.scalars().all()
        return playlists

