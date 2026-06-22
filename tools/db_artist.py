from sqlalchemy import select, case, literal_column, func, desc, nulls_last
from sqlalchemy.orm import selectinload, load_only
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.db import get_db
from app.core.config import settings
from app.models import Album, Track, Artist, track_artists, TrackHit
from app.services.artwork_service import ArtworkService
from app.schemas.artist import ArtistsResponse
from app.schemas.album import AlbumBase
from app.schemas.track import TrackBrief
from app.schemas.common import ArtistBase

class TrackWithPath(TrackBrief):
    path: str

class ArtistDetail(ArtistBase):
    main_albums: list[AlbumBase]
    track_albums: list[AlbumBase]
    top_tracks: list[TrackWithPath]
    track_count: int

async def get_artist_chars():
    # OK
    async for db in get_db():
        result = await db.execute(select(Artist.pinyin_initial).distinct().order_by(Artist.pinyin_initial))
        list_chars = [char for char, in result.all()]
        chars = [chr(char) for char in range(ord('A'), ord('Z')+1)] + ['_']
        start_chars = list(map(lambda x: (x, True) if x in list_chars else (x, False), chars))
        print(start_chars)
async def get_start_char_artists(start_char: str, without_path: bool = False):
    # OK
    async for db in get_db():
        result = await db.execute(select(Artist.id, Artist.name).filter(Artist.pinyin_initial == start_char).order_by(Artist.name))
        artists = [{'id': artist.id, 'name': artist.name} for artist in result.all()]
        print(len(artists))
        if without_path:
            service = ArtworkService(db=db, settings=settings)
            artists_without_path = [artist for artist in artists if not service.has_artist_directory(artist['name'])]
            print(artists_without_path)
            print(len(artists_without_path))
        else:
            for artist in artists:
                print(artist)
async def _get_artist_albums_separated(db: AsyncSession, artist_id: int):
    # OK
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
    result = await db.execute(select(subq))
    for row in result:
        album = Album(id=row.id, title=row.title, cover_art_hash=row.cover_art_hash)
        if row.album_type == 'main':
            main_albums.append(album)
        else:
            track_albums.append(album)

    return main_albums, track_albums
async def _get_top_tracks(db: AsyncSession, artist_id: int, top_count: int = 20):
    # OK
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
            load_only(Track.id, Track.title, Track.cover_art_hash, Track.path),
            selectinload(Track.artists).load_only(Artist.name),
        )
    )
    result = await db.execute(main_stmt)
    tracks = result.scalars().all()
    return tracks
async def get_artist_detail(artist_id: int, top_count = 20):
    # OK
    async for db in get_db():
        artist = await db.get(Artist, artist_id)
        main_albums, track_albums = await _get_artist_albums_separated(db, artist_id)
        top_tracks = await _get_top_tracks(db, artist_id, top_count)
        track_count = await db.scalar(
            select(func.count(Track.id))
            .join(track_artists, Track.id == track_artists.c.track_id)
            .where(track_artists.c.artist_id == artist_id)
        )
        artist.main_albums = main_albums
        artist.track_albums = track_albums
        artist.top_tracks = top_tracks
        artist.track_count = track_count
        print(ArtistDetail.model_validate(artist).model_dump_json(indent=2, ensure_ascii=False))
async def get_ten_artists(user_id: int = 1):
    # OK
    async for db in get_db():
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
                load_only(Artist.id, Artist.name)
            )
        )
        result_6 = await db.execute(stmt)
        top_artists = result_6.scalars().all()

        # 获取4个随机艺术家
        real_top_artists_num = len(top_artists) # 处理最常播放艺术家不足6个的情况
        result_4 = await db.execute(select(Artist).order_by(func.random()).limit(10 - real_top_artists_num))
        random_artists = result_4.scalars().all()

        result = top_artists + random_artists
        print(ArtistsResponse.model_validate(result).model_dump_json(indent=4, ensure_ascii=False))

async def get_artist_tracks(artist_id: int):
    # OK
    async for db in get_db():
        stmt = (
            select(Track)
            .join(track_artists, Track.id == track_artists.c.track_id)
            .where(track_artists.c.artist_id == artist_id)
            .options(
                load_only(Track.id, Track.title),
                selectinload(Track.artists).load_only(Artist.name)
            )
        )
        result = await db.execute(stmt)
        tracks = result.scalars().all()
        for track in tracks:
            print(track.id, track.title, [artist.name for artist in track.artists])

async def get_artist_track_records(artist_id: int):
    # OK
    async for db in get_db():
        stmt = (
            select(track_artists)
            .where(track_artists.c.artist_id == artist_id)
        )
        result = await db.execute(stmt)
        records = result.scalars().all()
        for record in records:
            print(record.track_id, record.artist_id)

async def find_artist_image_in_directory(artist_name: str, img_cate: str):
    from app.services.artwork_service import ArtworkService
    
    async for db in get_db():
        service = ArtworkService(db, settings)
        img_path = await service.find_artist_image_in_directory(artist_name, img_cate)
    print(str(img_path))

if __name__ == '__main__':
    # import sys
    # if len(sys.argv) != 3: sys.exit(1)
    # funct = sys.argv[1]
    # arg = sys.argv[2]
    import asyncio
    # if funct == 'a':
    #     asyncio.run(get_start_char_artists(arg))
    # elif funct == 'd':
    #     asyncio.run(get_artist_detail(int(arg)))
    # artist: 516-bandari, 740-Alin
    asyncio.run(find_artist_image_in_directory('A-Lin', 'face'))