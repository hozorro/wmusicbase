# -*- encoding: utf-8 -*-
'''
@File      :   artist_service.py
@Time      :   2025/11/29 19:42:16
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   artist service
'''


from fastapi import Request
from sqlalchemy import select, literal_column, case, func, desc, nulls_last
from sqlalchemy.orm import load_only, selectinload
from app.core.deps import SettingsDep, DbDep
from app.models.artist import Artist
from app.models.album import Album
from app.models.track import Track, track_artists
from app.models.playback import TrackHit, ArtistFav
from app.services.artwork_service import ArtworkService

class ArtistService:
    def __init__(self, db: DbDep, settings: SettingsDep, requst: Request):
        self.db = db
        self.settings = settings
        self.current_user_id = requst.state.user_id

    # region common use
    async def get_artist_chars(self) -> list[tuple[str, bool]]:
        result = await self.db.execute(select(Artist.pinyin_initial).distinct().order_by(Artist.pinyin_initial))
        list_chars = [char for char, in result.all()]
        chars = [chr(char) for char in range(ord('A'), ord('Z')+1)] + ['_']
        start_chars = list(map(lambda x: (x, True) if x in list_chars else (x, False), chars))
        return start_chars
    
    async def get_start_char_artists(self, start_char: str, without_path: bool = False) -> list[dict]:
        result = await self.db.execute(
            select(Artist)
            .filter(Artist.pinyin_initial == start_char)
            .options(
                load_only(Artist.id, Artist.name, Artist.pinyin_initial, Artist.cover_art_hash)
            )
        )
        artists = result.scalars().all()
        if without_path:
            service = ArtworkService(self.db, self.settings)
            artists_without_path = [artist for artist in artists if not service.has_artist_directory(artist['name'])]
            return artists_without_path
        return artists
    
    async def _get_artist_albums_separated(self, artist_id: int) -> tuple[list[Album], list[Album]]:
        subq = (
            select(
                Album,
                case(
                    (Album.album_artist_id == artist_id, literal_column("'main'")),
                    else_=literal_column("'track'")
                ).label('album_type')
            )
            .select_from(Album)
            .outerjoin(Track, Track.album_id == Album.id)
            .outerjoin(track_artists, Track.id == track_artists.c.track_id)
            .where(
                (Album.album_artist_id == artist_id) |
                (track_artists.c.artist_id == artist_id)
            )
            .distinct()
        ).subquery()

        main_albums = []    # as album artist
        track_albums = []   # not as album artist
        result = await self.db.execute(select(subq))
        for row in result:
            album = Album(id=row.id, title=row.title, cover_art_hash=row.cover_art_hash)
            if row.album_type == 'main':
                main_albums.append(album)
            else:
                track_albums.append(album)

        return main_albums, track_albums
    
    async def _get_top_tracks(self, artist_id: int, top_count: int) -> list[Track]:
        hit_count_subq = (
            select(
                TrackHit.track_id,
                func.count(TrackHit.id).label('total_hit_count')
            ).group_by(TrackHit.track_id).subquery()
        )
        artist_tracks_subq = (
            select(Track.id)
            .join(track_artists, Track.id == track_artists.c.track_id)
            .where(
                track_artists.c.artist_id == artist_id,
                Track.is_deleted == False
            )   # need not add ".subquery()" here, or warning "SAWarning: Coercing Subquery object into a select() for use in IN(); please pass a select() construct explicitly"
        )
        main_stmt = (
            select(
                Track,
                func.coalesce(hit_count_subq.c.total_hit_count, 0).label('hit_count')
            )
            .outerjoin(hit_count_subq, Track.id == hit_count_subq.c.track_id)
            .where(Track.id.in_(artist_tracks_subq))
            .order_by(
                desc(func.coalesce(hit_count_subq.c.total_hit_count, 0)),
                nulls_last(desc(Track.updated_at))
            )
            .limit(top_count)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash),
                selectinload(Track.artists).load_only(Artist.name),
            )
        )
        result = await self.db.execute(main_stmt)
        tracks = result.scalars().all()
        return tracks
    
    # endregion common use
    
    # region backend use
    async def get_artist(self, artist_id: int) -> dict | None:
        artist = await self.db.get(Artist, artist_id)
        if artist is None:
            return None
        main_albums, track_albums = await self._get_artist_albums_separated(artist_id)
        return {
            'id': artist.id,
            'name': artist.name,
            'main_albums': main_albums,
            'track_albums': track_albums,
        }
    # endregion backend use
    
    # region frontend use
    async def get_artist_detail(self, artist_id: int, top_count = 20) -> dict | None:
        '''get artist detail, including albums, total track numbers, and top20 tracks'''
        artist = await self.db.get(Artist, artist_id)
        if artist is None:
            return None
        main_albums, track_albums = await self._get_artist_albums_separated(artist_id)
        track_count = await self.db.scalar(
            select(func.count(Track.id))
            .join(track_artists, Track.id == track_artists.c.track_id)
            .where(track_artists.c.artist_id == artist_id)
        )
        # get top 20 tracks of the artist
        top_tracks = await self._get_top_tracks(artist_id, top_count)
        artist.main_albums = main_albums
        artist.track_albums = track_albums
        artist.track_count = track_count
        artist.top_tracks = top_tracks
        return artist
        
    async def get_ten_artists(self, user_id: int = 1) -> list[dict]:
        '''get 10 artists, including 6 most played artists and 4 random artists'''
        stmt = (
            select(Artist)
            .join(track_artists, Artist.id == track_artists.c.artist_id)
            .join(Track, Track.id == track_artists.c.track_id)
            .join(TrackHit, Track.id == TrackHit.track_id)
            .where(TrackHit.user_id == user_id)
            .having(func.count(TrackHit.id) > 0)
            .group_by(Artist.id)
            .order_by(desc(func.count(TrackHit.id)))
            .limit(6)
            .options(
                load_only(Artist.id, Artist.name, Artist.cover_art_hash)
            )
        )
        result_6 = await self.db.execute(stmt)
        top_artists = result_6.scalars().all()

        # get 4 random artists
        real_top_artists_num = len(top_artists) # handle the case that most played artists number is less than 6
        result_4 = await self.db.execute(select(Artist).order_by(func.random()).limit(10 - real_top_artists_num))
        random_artists = result_4.scalars().all()

        return top_artists + random_artists
    
    async def get_favorited_artists(self) -> list[dict]:
        '''get favorited artists'''
        stmt = (
            select(Artist)
            .join(ArtistFav, Artist.id == ArtistFav.artist_id)
            .where(ArtistFav.user_id == self.current_user_id)
            .options(
                load_only(Artist.id, Artist.name, Artist.cover_art_hash)
            )
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    # endregion frontend use    