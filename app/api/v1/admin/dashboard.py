# -*- encoding: utf-8 -*-
'''
@File      :   dashboard.py
@Time      :   2025/10/25 11:16:24
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   dashboard api router
'''


from asyncache import cached
import psutil, platform
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, __version__ as fastapi_version, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.cache import lru_cache
from app.core.deps import DbDep, AdminDep
from app.core.config import settings
from app.core.state import system_state
from app.models import Track, Album, Artist, Folder, Genre, Playlist, track_artists, TrackHit
from app.services.sync import Syncer
from app.schemas.common import ResponseModel
from app.schemas.sysinfo import DashboardInfo

router = APIRouter()

#============= basic statistics ============
async def _get_basic_stats(db: AsyncSession):
    track_count = await db.scalar(select(func.count(Track.id)).where(Track.is_deleted == False))
    album_count = await db.scalar(select(func.count(Album.id)))
    artist_count = await db.scalar(select(func.count(Artist.id)))
    folder_count = await db.scalar(select(func.count(Folder.id)))
    genre_count = await db.scalar(select(func.count(Genre.id)))
    playlist_count = await db.scalar(select(func.count(Playlist.id)))
    general_stats = {
        'track_count': track_count or 0,
        'album_count': album_count or 0,
        'artist_count': artist_count or 0,
        'folder_count': folder_count or 0,
        'genre_count': genre_count or 0,
        'playlist_count': playlist_count or 0,
    }
    artists_tracks_count = await db.execute(
        select(Artist.id, Artist.name, func.count(Track.id).label('track_count'))
        .join(track_artists, track_artists.c.artist_id == Artist.id)
        .join(Track, Track.id == track_artists.c.track_id)
        .group_by(Artist.id)
        .order_by(func.count(Track.id).desc())
        .limit(20)
    )
    latest_added_tracks = await db.execute(
        select(Track.id, Track.title, Track.created_at)
        .order_by(Track.created_at.desc())
        .limit(5)
    )
    stats = {
        'general': general_stats,
        'artist_tracks_stats': [{'id': a.id, 'name': a.name, 'track_count': a.track_count} for a in artists_tracks_count],
        'latest_added_tracks_stats': [{'id': t.id, 'title': t.title, 'created_at': t.created_at} for t in latest_added_tracks],
    }
    return stats
#============= playback statistics ============
async def _get_playback_stats(db: AsyncSession):
    recent = await db.execute(
        select(Track.id, Track.title)
        .join(TrackHit)
        .order_by(TrackHit.played_at.desc())
        .limit(4)
    )

    top_played_artists = await db.execute(
        select(Artist, func.count(TrackHit.id).label('play_count'))
        .join(track_artists, Artist.id == track_artists.c.track_id)
        .join(Track, Track.id == track_artists.c.track_id)
        .join(TrackHit, TrackHit.track_id == Track.id)
        .group_by(Artist.id)
        .order_by(func.count(TrackHit.id).desc())
        .limit(5)
    )

    total_played = await db.scalar(select(func.count(TrackHit.id)))

    stats = {
        'total_played': total_played or 0,
        'recent_tracks': [{'id': t.id, 'title': t.title} for t in recent],
        'top_artists': [{'id': a.id, 'name': a.name, 'play_count': a.play_count} for a in top_played_artists],
    }
    return stats

@router.get('/stats', response_model=ResponseModel[DashboardInfo])
@cached(lru_cache)
async def get_dashboard_stats(
    db: DbDep,
    current_user: AdminDep
):
    if system_state.is_scanning:
        return ResponseModel(
            code=200,
            msg='ok',
            data={
                'system_status': 'busy',
                'current_user': current_user.username,
                'basic_stats': {},
                'playback_stats': {},
                'system_info': {},
                'watcher_info': {},
                'scan_info': {}
            }
        )
    # basic stats
    basic_stats = await _get_basic_stats(db)
    playback_stats = await _get_playback_stats(db)
    # system info
    uptime = datetime.now(timezone.utc) - datetime.fromtimestamp(psutil.boot_time(), timezone.utc)
    system_info = {
        'system': platform.system(),
        'python_version': platform.python_version(),
        'fastapi_version': fastapi_version,
        'server_uptime': str(timedelta(seconds=int(uptime.total_seconds())))
    }
    # watcher status
    watcher_info = {
        'is_running': system_state.is_watcher_running,
        'watcher_path': str(settings.MUSIC_LIBRARY_PATH)
    }
    # scanning status
    scan_info = {
        'is_running': system_state.is_scanning,
        'progress': system_state.scan_progress
    }
    return ResponseModel(
        code=200,
        msg='ok',
        data=DashboardInfo.model_validate({
            'system_status': 'ready',
            'current_user': current_user.username,
            'basic_stats': basic_stats,
            'playback_stats': playback_stats,
            'system_info': system_info,
            'watcher_info': watcher_info,
            'scan_info': scan_info
        })
    )

@router.post('/initializemeta', response_model=ResponseModel[None])
async def initialize_meta(db: DbDep):
    syncer = Syncer(db, settings)
    await syncer.initialize_sync_meta()
    return ResponseModel(code=200, msg='ok')