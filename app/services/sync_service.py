# -*- encoding: utf-8 -*-
'''
@File      :   sync_service.py
@Time      :   2026/08/06 10:00:00
@Author    :   enauvy
@Version   :   2.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   sync service: summary & paginated incremental pull
               for frontend indexeddb sync
'''


from datetime import datetime, timezone
from fastapi import Request
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload, load_only
from app.core.deps import DbDep
from app.models import (
    Album, Artist, ArtistFav, ArtistHit, Folder, Genre, Playlist,
    PlaylistHit, PlaylistTrack, Track, TrackFav, TrackHit, track_artists
)
from app.schemas.sync import (
    SyncAlbum, SyncArtist, SyncArtistRef, SyncFolder, SyncGenre,
    SyncPlaylist, SyncPlaylistTrackRef, SyncTrack
)


class SyncService:
    def __init__(self, db: DbDep, request: Request):
        self.db = db
        self.current_user_id = request.state.user_id

    # region summary
    async def get_summary(self, since: datetime | None = None) -> dict:
        '''
        Get sync summary: live counts of six stores, deleted ids (incremental only)
        and the server time snapshot.
        - full sync (since is None): counts of all live (not soft-deleted) records
        - incremental sync: counts of live records changed since `since`,
          plus soft-deleted ids changed since `since`
        '''
        counts: dict[str, int] = {}
        for store, count in [
            ('tracks', await self._count(Track, Track.is_deleted == False, since)),
            ('albums', await self._count(Album, None, since)),
            ('artists', await self._count(Artist, None, since)),
            ('genres', await self._count(Genre, None, since)),
            ('folders', await self._count(Folder, None, since)),
            ('playlists', await self._count(
                Playlist, Playlist.is_deleted == False, since, user_scoped=True)),
        ]:
            counts[store] = count

        deleted = None
        if since is not None:
            deleted = {}
            for store, model in [('tracks', Track), ('playlists', Playlist)]:
                stmt = select(model.id).where(
                    model.is_deleted == True, model.updated_at > since)
                if store == 'playlists':
                    stmt = stmt.where(model.user_id == self.current_user_id)
                ids = (await self.db.execute(stmt.order_by(model.id))).scalars().all()
                if ids:
                    deleted[store] = ids

        return {
            'counts': counts,
            'deleted': deleted,
            'serverTime': datetime.now(tz=timezone.utc),
        }

    async def _count(self, model, live_cond, since: datetime | None, user_scoped: bool = False) -> int:
        stmt = select(func.count(model.id))
        conds = [c for c in [live_cond] if c is not None]
        if since is not None:
            conds.append(model.updated_at > since)
        if user_scoped:
            conds.append(model.user_id == self.current_user_id)
        if conds:
            stmt = stmt.where(*conds)
        return await self.db.scalar(stmt) or 0
    # endregion

    # region pull
    async def pull(self, store: str, since: datetime | None = None,
                   after_id: int = 0, size: int = 200) -> dict:
        '''
        Pull a page of records of the given store, ordered by id ascending.
        - since is None: full pull of all live records
        - since given: incremental pull of live records changed since `since`
        Returns {'items': [...], 'next_after_id': int | None}.
        '''
        pullers = {
            'tracks': self._pull_tracks,
            'albums': self._pull_albums,
            'artists': self._pull_artists,
            'genres': self._pull_genres,
            'folders': self._pull_folders,
            'playlists': self._pull_playlists,
        }
        return await pullers[store](since, after_id, size)

    def _page_conds(self, model, since: datetime | None, after_id: int, extra=None) -> list:
        conds = [model.id > after_id]
        if since is not None:
            conds.append(model.updated_at > since)
        if extra is not None:
            conds.append(extra)
        return conds

    def _next_after_id(self, items, size: int) -> int | None:
        return items[-1].id if len(items) == size else None

    async def _pull_tracks(self, since: datetime | None, after_id: int, size: int) -> dict:
        stmt = (
            select(Track)
            .where(*self._page_conds(Track, since, after_id, Track.is_deleted == False))
            .options(
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                selectinload(Track.album).load_only(Album.id, Album.title),
                selectinload(Track.genres).load_only(Genre.id),
            )
            .order_by(Track.id)
            .limit(size)
        )
        tracks = (await self.db.execute(stmt)).scalars().all()
        if not tracks:
            return {'items': [], 'next_after_id': None}

        track_ids = [t.id for t in tracks]

        # favorites of current user
        fav_map: dict[int, datetime] = {}
        fav_rows = (await self.db.execute(
            select(TrackFav.track_id, TrackFav.favorited_at).where(
                TrackFav.user_id == self.current_user_id,
                TrackFav.track_id.in_(track_ids)
            )
        )).all()
        fav_map = {track_id: favorited_at for track_id, favorited_at in fav_rows}

        # play hits of current user (cap per track to avoid oversized payload)
        hits_cap = 200
        hits_map: dict[int, list[datetime]] = {}
        hit_rows = (await self.db.execute(
            select(TrackHit.track_id, TrackHit.played_at)
            .where(
                TrackHit.user_id == self.current_user_id,
                TrackHit.track_id.in_(track_ids)
            )
            .order_by(TrackHit.track_id, TrackHit.played_at, TrackHit.id)
        )).all()
        for track_id, played_at in hit_rows:
            bucket = hits_map.setdefault(track_id, [])
            if len(bucket) < hits_cap:
                bucket.append(played_at)

        items = [
            SyncTrack(
                id=t.id,
                title=t.title,
                artists=[SyncArtistRef.model_validate(a) for a in t.artists],
                album=t.album,
                duration=t.duration,
                cover_art_hash=t.cover_art_hash,
                year=t.year,
                genre_ids=[g.id for g in t.genres],
                folder_id=t.folder_id,
                created_at=t.created_at,
                favorited_at=fav_map.get(t.id),
                hits=hits_map.get(t.id),
            ) for t in tracks
        ]
        return {'items': items, 'next_after_id': self._next_after_id(tracks, size)}

    async def _pull_artists(self, since: datetime | None, after_id: int, size: int) -> dict:
        track_count_subq = (
            select(func.count(track_artists.c.track_id))
            .where(
                track_artists.c.artist_id == Artist.id,
                track_artists.c.track_id == Track.id,
                Track.is_deleted == False,
            )
            .correlate(Artist)
            .scalar_subquery()
        )
        stmt = (
            select(Artist, track_count_subq.label('track_count'))
            .where(*self._page_conds(Artist, since, after_id))
            .order_by(Artist.id)
            .limit(size)
        )
        rows = (await self.db.execute(stmt)).all()
        if not rows:
            return {'items': [], 'next_after_id': None}

        artist_ids = [a.id for a, _ in rows]

        hit_map: dict[int, int] = {}
        hit_rows = (await self.db.execute(
            select(ArtistHit.artist_id, func.count(ArtistHit.id))
            .where(
                ArtistHit.user_id == self.current_user_id,
                ArtistHit.artist_id.in_(artist_ids)
            )
            .group_by(ArtistHit.artist_id)
        )).all()
        hit_map = {artist_id: count for artist_id, count in hit_rows}

        fav_map: dict[int, datetime] = {}
        fav_rows = (await self.db.execute(
            select(ArtistFav.artist_id, ArtistFav.favorited_at).where(
                ArtistFav.user_id == self.current_user_id,
                ArtistFav.artist_id.in_(artist_ids)
            )
        )).all()
        fav_map = {artist_id: favorited_at for artist_id, favorited_at in fav_rows}

        items = [
            SyncArtist(
                id=a.id,
                name=a.name,
                pinyin_initial=a.pinyin_initial,
                face_art_hash=a.face_art_hash,
                portrait_art_hash=a.portrait_art_hash,
                track_count=track_count or 0,
                favorited_at=fav_map.get(a.id),
                hit_count=hit_map.get(a.id),
            ) for a, track_count in rows
        ]
        return {'items': items, 'next_after_id': self._next_after_id([a for a, _ in rows], size)}

    async def _pull_albums(self, since: datetime | None, after_id: int, size: int) -> dict:
        stmt = (
            select(Album)
            .where(*self._page_conds(Album, since, after_id))
            .options(selectinload(Album.album_artist).load_only(Artist.id, Artist.name))
            .order_by(Album.id)
            .limit(size)
        )
        albums = (await self.db.execute(stmt)).scalars().all()
        if not albums:
            return {'items': [], 'next_after_id': None}

        album_ids = [a.id for a in albums]

        # track_count per album (live tracks only)
        count_rows = (await self.db.execute(
            select(Track.album_id, func.count(Track.id))
            .where(Track.album_id.in_(album_ids), Track.is_deleted == False)
            .group_by(Track.album_id)
        )).all()
        count_map = {album_id: count for album_id, count in count_rows}

        # artists union of all tracks per album
        artist_rows = (await self.db.execute(
            select(Track.album_id, Artist.id, Artist.name)
            .join(track_artists, track_artists.c.track_id == Track.id)
            .join(Artist, Artist.id == track_artists.c.artist_id)
            .where(Track.album_id.in_(album_ids), Track.is_deleted == False)
        )).all()
        artists_map: dict[int, dict[int, SyncArtistRef]] = {}
        for album_id, artist_id, artist_name in artist_rows:
            artists_map.setdefault(album_id, {})[artist_id] = \
                SyncArtistRef(id=artist_id, name=artist_name)

        items = [
            SyncAlbum(
                id=a.id,
                title=a.title,
                album_artist=a.album_artist,
                artists=list(artists_map.get(a.id, {}).values()),
                cover_art_hash=a.cover_art_hash,
                track_count=count_map.get(a.id, 0),
            ) for a in albums
        ]
        return {'items': items, 'next_after_id': self._next_after_id(albums, size)}

    async def _pull_genres(self, since: datetime | None, after_id: int, size: int) -> dict:
        stmt = (
            select(Genre)
            .where(*self._page_conds(Genre, since, after_id))
            .order_by(Genre.id)
            .limit(size)
        )
        genres = (await self.db.execute(stmt)).scalars().all()
        items = [SyncGenre.model_validate(g) for g in genres]
        return {'items': items, 'next_after_id': self._next_after_id(genres, size)}

    async def _pull_folders(self, since: datetime | None, after_id: int, size: int) -> dict:
        stmt = (
            select(Folder)
            .where(*self._page_conds(Folder, since, after_id))
            .order_by(Folder.id)
            .limit(size)
        )
        folders = (await self.db.execute(stmt)).scalars().all()
        items = [SyncFolder.from_model(f) for f in folders]
        return {'items': items, 'next_after_id': self._next_after_id(folders, size)}

    async def _pull_playlists(self, since: datetime | None, after_id: int, size: int) -> dict:
        stmt = (
            select(Playlist)
            .where(*self._page_conds(
                Playlist, since, after_id,
                Playlist.is_deleted == False
            ), Playlist.user_id == self.current_user_id)
            .order_by(Playlist.id)
            .limit(size)
        )
        playlists = (await self.db.execute(stmt)).scalars().all()
        if not playlists:
            return {'items': [], 'next_after_id': None}

        playlist_ids = [p.id for p in playlists]

        # positions of playlist tracks
        pt_rows = (await self.db.execute(
            select(PlaylistTrack.playlist_id, PlaylistTrack.track_id, PlaylistTrack.position)
            .where(PlaylistTrack.playlist_id.in_(playlist_ids))
            .order_by(PlaylistTrack.playlist_id, PlaylistTrack.position)
        )).all()
        tracks_map: dict[int, list[SyncPlaylistTrackRef]] = {}
        for playlist_id, track_id, position in pt_rows:
            tracks_map.setdefault(playlist_id, []).append(
                SyncPlaylistTrackRef(id=track_id, position=position))

        # hit counts of current user
        hit_rows = (await self.db.execute(
            select(PlaylistHit.playlist_id, func.count(PlaylistHit.id))
            .where(
                PlaylistHit.user_id == self.current_user_id,
                PlaylistHit.playlist_id.in_(playlist_ids)
            )
            .group_by(PlaylistHit.playlist_id)
        )).all()
        hit_map = {playlist_id: count for playlist_id, count in hit_rows}

        items = [
            SyncPlaylist(
                id=p.id,
                title=p.title,
                comment=p.comment,
                cover_art_hash=p.cover_art_hash,
                created_at=p.created_at,
                tracks=tracks_map.get(p.id, []),
                hit_count=hit_map.get(p.id),
            ) for p in playlists
        ]
        return {'items': items, 'next_after_id': self._next_after_id(playlists, size)}
    # endregion
