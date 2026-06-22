from sqlalchemy import select, func, desc, nulls_last
from sqlalchemy.orm import selectinload, load_only, joinedload
from app.core.db import get_db
from app.models import Track, TrackHit, TrackFav, Artist, Album
from app.schemas.track import TrackBriefsResponse

async def get_more_track_info():
    async for db in get_db():
        stmt = select(Track).where(Track.id == 6468).options(
            selectinload(Track.play_hits.and_(TrackHit.user_id == 1)).options(
                load_only(TrackHit.played_at)
            ),
        )
        
        result = await db.execute(stmt)
        tracks = result.scalar_one_or_none()
        print({
            'title': tracks.title,
            'duration': tracks.duration,
            'bitrate': tracks.bitrate,
            'bitrate_mode': tracks.bitrate_mode,
            'year': tracks.year,
            'acounstid_id': tracks.acoustid_id,
            'mb_trackid': tracks.mb_trackid,
            'play_hits': [hit.played_at.isoformat() for hit in tracks.play_hits]
        })

async def get_track_info(track_id: int):
    async for db in get_db():
        hit_subq = (
            select(
                TrackHit.track_id,
                func.count(TrackHit.id).label('hit_count')
            ).group_by(TrackHit.track_id)
            .where(TrackHit.user_id == 1)
            .subquery()
        )
        fav_subq = (
            select(
                TrackFav.track_id,
                TrackFav.favorited_at,
            ).where(
                TrackFav.track_id == track_id, 
                TrackFav.user_id == 1
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
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )
        result = await db.execute(stmt)
        row = result.first()
        if not row:
            print('Track not found')
        
        track, hit_count, favorited_at = row
        track.hit_count = hit_count
        track.favorited_at = favorited_at
        print({
            'id': track.id,
            'title': track.title,
            'duration': track.duration,
            'cover_art_hash': track.cover_art_hash,
            'artists': [artist.name for artist in track.artists],
            'album': track.album.title,
            'hit_count': track.hit_count,
            'favorited_at': track.favorited_at,
        })
async def get_most_played_tracks(user_id: int = 1, limit: int | None = 12):
    async for db in get_db():
        hit_count_subq = (
            select(
                TrackHit.track_id,
                func.count(TrackHit.id).label('total_hit_count')
            )
            .where(TrackHit.user_id == user_id)
            .group_by(TrackHit.track_id)
            .subquery()
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
                load_only(Track.id, Track.title),
                selectinload(Track.artists).load_only(Artist.name),
            )
        )
        
        result = await db.execute(main_stmt)
        tracks = result.scalars().all()
        print(TrackBriefsResponse
            .model_validate(tracks)
            .model_dump_json(indent=4, ensure_ascii=False))
        
def get_track_count():
    from pathlib import Path
    root_path = r'H:\musiclibcorrect'
    mp3_count = len(list(Path(root_path).rglob('*.mp3')))
    flac_count = len(list(Path(root_path).rglob('*.flac')))
    print(f'total: {mp3_count + flac_count}')

async def get_track_art(track_id: int):
    from app.services.artwork_service import ArtworkService
    from app.core.config import settings
    async for db in get_db():
        service = ArtworkService(db, settings)
        track_art = await service.get_or_cache_track_artwork(track_id)
        print(str(track_art))
        
if __name__ == '__main__':
    import asyncio
    asyncio.run(get_track_art(7185))
    # get_track_count()