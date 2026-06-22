from sqlalchemy import select, func, desc
from sqlalchemy.orm import selectinload, load_only, joinedload
from app.core.db import get_db
from app.models import Playlist, Track, PlaylistHit, User, Artist, PlaylistTrack
from app.schemas.playback import PlaylistsResponse, PlaylistResponse

async def get_top_playlists(user_id: int = 1):
    async for db in get_db():
        stmt = (
            select(Playlist.id, Playlist.title, func.count(PlaylistHit.id).label('hit_count') )
            .join(PlaylistHit, PlaylistHit.playlist_id == Playlist.id)
            .where(Playlist.user_id == user_id)
            .group_by(Playlist.id)
            .order_by(desc('hit_count'), Playlist.updated_at.desc())
            .limit(6)
        )
        result = await db.execute(stmt)
        playlists = result.scalars().all()
        print(PlaylistsResponse
            .model_validate(playlists)
            .model_dump_json(indent=4, ensure_ascii=False)
        )

async def get_playlist_info(playlist_id: int):
    async for db in get_db():
        stmt = (
            select(Playlist)
            .where(Playlist.id == playlist_id)
            .options(
                joinedload(Playlist.user).load_only(User.username),
                selectinload(Playlist.tracks).options(
                    load_only(Track.id, Track.title),
                    selectinload(Track.artists).load_only(Artist.name)
                )
                .order_by(PlaylistTrack.position.asc())
            )
        )
        result = await db.execute(stmt)
        playlist = result.scalar_one_or_none()
        if playlist:
            print(
                PlaylistResponse.model_validate(playlist)
                .model_dump_json(indent=4, ensure_ascii=False)
            )

if __name__ == '__main__':
    import asyncio
    asyncio.run(get_top_playlists())