# -*- encoding: utf-8 -*-
'''
@File      :   netease_service.py
@Time      :   2025/01/01 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   netease playlist import service
'''



import json
import re
import httpx
from urllib.parse import urlparse, parse_qs
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload, joinedload, load_only
from app.core.deps import SettingsDep, DbDep
from app.core.exceptions import BusinessException
from app.core.logger import logger
from app.models import Track, Artist, Album, Playlist
from app.schemas.netease import (
    NeteaseTrackInfo,
    NeteasePlaylistResponse,
    NeteaseMatchTrackItem,
    NeteaseMatchCandidate,
    NeteaseMatchResult,
    NeteaseUnmatchedItem,
    NeteaseMatchResponse,
)
from app.services.artwork_service import ArtworkService

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Safari/537.36 Chrome/91.0.4472.164 NeteaseMusicDesktop/2.10.2.200154'
REFERER = 'https://music.163.com/'
DEFAULT_COOKIES = {
    "os": "pc",
    "appver": "",
    "osver": "",
    "deviceId": "pyncm!"
}

def load_cookies(cookie_file: str):
    with open(cookie_file, 'r') as f:
        cookies = json.load(f)
    return cookies

class NeteaseService:
    '''netease playlist import service'''

    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

        self.cookies = load_cookies(self.settings.NETEASE_COOKIES_FILE)
    
    @staticmethod
    async def extract_playlist_id(share_text: str) -> str | None:
        """
        Extract playlist ID from netease music share text.

        Args:
            share_text: similar to "分享歌单: 震撼音乐 https://163cn.tv/bglqb7KP (@网易云音乐)"

        Returns:
            Playlist ID string, returns None on failure.
        """
        # 1. Extract short link
        url_pattern = r'https?://163cn\.tv/[A-Za-z0-9]+'
        match = re.search(url_pattern, share_text)
        if not match:
            logger.warning(f'Valid 163cn.tv short link not found in share text: {share_text}')
            return None
        short_url = match.group(0)

        # 2. Restore the real address
        headers = {
            'User-Agent': USER_AGENT,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                # Use HEAD method to only get the response header, follow redirects to get the final URL
                resp = await client.head(short_url, headers=headers)
                final_url = str(resp.url)
        except Exception as e:
            logger.error(f'Short link parsing failed: {e}')
            return None

        # Some short links may not redirect via HTTP (e.g., JS redirect), in which case final_url will still be the short link
        if final_url == short_url:
            # Fallback: Use GET request to find the real link from the response body
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(short_url, headers=headers)
                    # 尝试从 HTML 或 JS 中提取 music.163.com 链接
                    fallback = re.search(r'https?://music\.163\.com/[^\s"\'<>]+', resp.text)
                    if fallback:
                        final_url = fallback.group(0)
                    else:
                        logger.warning('Failed to parse the real address from the short link response')
                        return None
            except Exception as e:
                logger.error(f'Short link GET request failed: {e}')
                return None

        # 3. Extract id parameter from the URL
        parsed = urlparse(final_url)
        query = parse_qs(parsed.query)
        playlist_id = query.get('id', [None])[0]

        if playlist_id:
            return playlist_id
        else:
            return None

    async def fetch_playlist(self, playlist_id: int) -> NeteasePlaylistResponse:
        '''
        fetch playlist from netease api
        Args:
            playlist_id: netease playlist id
        Returns:
            NeteasePlaylistResponse with playlist info and tracks
        Raises:
            BusinessException: when api request fails or playlist not found
        '''
        # url = f'{self.api_base}?id={playlist_id}'
        headers = {
            'User-Agent': USER_AGENT,
            'Referer': REFERER,
            'Accept': '*/*',
        }
        request_cookies = DEFAULT_COOKIES.copy()
        request_cookies.update(self.cookies)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.settings.NETEASE_PLAYLIST_API, data={'id': playlist_id}, headers=headers, cookies=request_cookies, timeout=30)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f'Netease API HTTP error: {e.response.status_code} for playlist {playlist_id}')
            raise BusinessException(
                code=30521,
                msg=f'netease api request failed: {e.response.status_code}',
                status_code=502
            )
        except httpx.RequestError as e:
            logger.error(f'Netease API request error: {e} for playlist {playlist_id}')
            raise BusinessException(
                code=30522,
                msg='netease api request failed: network error',
                status_code=502
            )
        except Exception as e:
            logger.error(f'Netease API unexpected error: {e} for playlist {playlist_id}')
            raise BusinessException(
                code=30523,
                msg='netease api request failed: unknown error',
                status_code=502
            )

        # check response code
        if data.get('code') != 200:
            logger.warning(f'Netease playlist {playlist_id} not found or error: {data}')
            raise BusinessException(
                code=30524,
                msg='playlist not found on netease',
                status_code=404
            )

        playlist_data = data.get('playlist', {})
        if not playlist_data:
            raise BusinessException(
                code=30524,
                msg='playlist not found on netease',
                status_code=404
            )

        # parse tracks
        tracks = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                track_ids = [str(t['id']) for t in playlist_data.get('trackIds', [])]
                for i in range(0, len(track_ids), 100):
                    batch_ids = track_ids[i:i+100]
                    song_data = {'c': json.dumps([{'id': int(sid), 'v': 0} for sid in batch_ids])}
                    song_resp = await client.post(self.settings.NETEASE_SONG_API, data=song_data, headers=headers, cookies=request_cookies, timeout=30)
                    song_resp.raise_for_status()
                    song_result = song_resp.json()
                    for song in song_result.get('songs', []):
                        tracks.append({
                            'id': song['id'],
                            'name': song['name'],
                            'mainTitle': song['mainTitle'],
                            'artists': [ar['name'] for ar in song['ar']],
                            'album': song['al']['name'],
                            'duration': song['dt'],
                        })
        except Exception as e:
            raise BusinessException(
                code=30525,
                msg='netease api request failed: song data processing error',
                status_code=502
            )

        return NeteasePlaylistResponse(
            id=playlist_data.get('id', playlist_id),
            name=playlist_data.get('name', ''),
            coverImgUrl=playlist_data.get('coverImgUrl', ''),
            trackCount=playlist_data.get('trackCount', len(tracks)),
            tracks=tracks
        )

    async def match_tracks(self, tracks: list[NeteaseMatchTrackItem]) -> NeteaseMatchResponse:
        '''
        match netease tracks against local music library
        Args:
            tracks: list of netease track info
        Returns:
            NeteaseMatchResponse with matched and unmatched tracks
        '''
        matched = []
        unmatched = []

        for index, track in enumerate(tracks):
            candidates = await self._find_match_candidates(track)
            if candidates:
                matched.append(NeteaseMatchResult(
                    netease_index=index,
                    netease_name=track.name,
                    netease_artists=track.artists,
                    netease_album=track.album,
                    candidates=candidates
                ))
            else:
                unmatched.append(NeteaseUnmatchedItem(
                    netease_index=index,
                    netease_name=track.name,
                    netease_artists=track.artists,
                    netease_album=track.album
                ))

        return NeteaseMatchResponse(
            matched=matched,
            unmatched=unmatched,
            total=len(tracks),
            matched_count=len(matched),
            unmatched_count=len(unmatched)
        )

    async def _find_match_candidates(self, track: NeteaseMatchTrackItem, limit: int = 5) -> list[NeteaseMatchCandidate]:
        '''
        find matching local tracks for a netease track
        priority: exact match > fuzzy match with artist > fuzzy match title only
        Args:
            track: netease track info
            limit: max candidates to return
        Returns:
            list of matched local track candidates
        '''
        candidates = []
        seen_ids = set()

        # normalize inputs
        # use mainTitle if available, otherwise use name
        title = track.mainTitle.strip() if track.mainTitle and track.mainTitle.strip() else track.name.strip()
        artists = [a.strip() for a in track.artists if a.strip()]
        album = track.album.strip() if track.album else ''

        # strategy 1: exact match (title + any artist + album)
        if artists and album:
            exact_candidates = await self._search_tracks(
                title=title,
                artist_names=artists,
                album_title=album,
                exact=True,
                limit=limit
            )
            for c in exact_candidates:
                if c.track_id not in seen_ids:
                    candidates.append(c)
                    seen_ids.add(c.track_id)

        # strategy 2: match title + any artist (ignore album)
        if len(candidates) < limit and artists:
            fuzzy_candidates = await self._search_tracks(
                title=title,
                artist_names=artists,
                album_title=None,
                exact=False,
                limit=limit - len(candidates)
            )
            for c in fuzzy_candidates:
                if c.track_id not in seen_ids:
                    candidates.append(c)
                    seen_ids.add(c.track_id)

        # strategy 3: match title only
        if len(candidates) < limit:
            title_candidates = await self._search_tracks(
                title=title,
                artist_names=None,
                album_title=None,
                exact=False,
                limit=limit - len(candidates)
            )
            for c in title_candidates:
                if c.track_id not in seen_ids:
                    candidates.append(c)
                    seen_ids.add(c.track_id)

        return candidates

    async def _search_tracks(
        self,
        title: str,
        artist_names: list[str] | None = None,
        album_title: str | None = None,
        exact: bool = False,
        limit: int = 5
    ) -> list[NeteaseMatchCandidate]:
        '''
        search local tracks with filters
        Args:
            title: track title to search
            artist_names: list of artist names, match if any artist matches (optional)
            album_title: album title to filter (optional)
            exact: whether to use exact match or fuzzy match
            limit: max results
        Returns:
            list of matched local tracks
        '''
        # build base query
        stmt = (
            select(Track)
            .where(Track.is_deleted == False)
            .options(
                load_only(Track.id, Track.title, Track.cover_art_hash, Track.duration),
                selectinload(Track.artists).load_only(Artist.id, Artist.name),
                joinedload(Track.album).load_only(Album.id, Album.title),
            )
        )

        # title filter
        if exact:
            stmt = stmt.where(func.lower(Track.title) == title.lower())
        else:
            stmt = stmt.where(Track.title.ilike(f'%{title}%'))

        # artist filter: match if any of the artist names matches
        if artist_names:
            # join with artists table
            stmt = stmt.join(Track.artists)
            # build OR conditions for multiple artists
            artist_conditions = []
            for artist_name in artist_names:
                if exact:
                    artist_conditions.append(func.lower(Artist.name) == artist_name.lower())
                else:
                    artist_conditions.append(Artist.name.ilike(f'%{artist_name}%'))
            # use OR to match any artist
            stmt = stmt.where(or_(*artist_conditions))

        # album filter
        if album_title:
            stmt = stmt.join(Track.album).where(
                Album.title.ilike(f'%{album_title}%') if not exact else func.lower(Album.title) == album_title.lower()
            )

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        tracks = result.scalars().unique().all()

        # convert to candidates
        candidates = []
        for t in tracks:
            candidates.append(NeteaseMatchCandidate(
                track_id=t.id,
                title=t.title,
                artists=[a.name for a in t.artists],
                album=t.album.title if t.album else '',
                duration=t.duration,
                cover_art_hash=t.cover_art_hash
            ))

        return candidates

    async def download_cover(self, url: str, playlist_id: int) -> str | None:
        '''
        download cover image from url and save as playlist artwork
        Args:
            url: cover image url
            playlist_id: local playlist id
        Returns:
            cover_art_hash if successful, None otherwise
        '''
        if not url:
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                content = response.content

            # validate content type
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                logger.warning(f'Invalid content type for cover: {content_type}')
                return None

            # save using artwork service
            artwork_service = ArtworkService(self.db, self.settings)
            img_path = await artwork_service._save_artwork_to_cache(playlist_id, 'playlist', content)
            if img_path:
                cover_art_hash = artwork_service.compute_file_hash(img_path)
                # update playlist cover_art_hash
                playlist = await self.db.get(Playlist, playlist_id)
                if playlist:
                    playlist.cover_art_hash = cover_art_hash
                    await self.db.commit()
                return cover_art_hash

        except Exception as e:
            logger.error(f'Failed to download cover from {url}: {e}')
            return None

        return None
