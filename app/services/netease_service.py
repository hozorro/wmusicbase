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
import time
import httpx
from urllib.parse import urlparse, parse_qs
from PIL import Image
from io import BytesIO
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload, joinedload, load_only
from app.core.deps import SettingsDep, DbDep
from app.core.exceptions import BusinessException
from app.core.logger import logger
from app.models import Track, Artist, Album, Playlist
from app.schemas.netease import (
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
SEARCH_API = 'https://music.163.com/api/cloudsearch/pc'
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

        cookies = DEFAULT_COOKIES.copy()
        self.cookies = cookies.update(load_cookies(self.settings.NETEASE_COOKIES_FILE))
    
    @staticmethod
    def _headers():
        return {
            'User-Agent': USER_AGENT,
            'Referer': REFERER,
            'Accept': '*/*',
        }
    
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
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.settings.NETEASE_PLAYLIST_API, 
                    data={'id': playlist_id}, 
                    headers=NeteaseService._headers(), 
                    cookies=self.cookies, 
                    timeout=30
                )
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
                    song_resp = await client.post(
                        self.settings.NETEASE_SONG_API, 
                        data=song_data, 
                        headers=NeteaseService._headers(), 
                        cookies=self.cookies
                    )
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

    # =========== lyric ===========
    async def search_song(self, keyword: str, page: int = 0, limit: int = 10) -> list[dict]:
        '''search song, return list of song info'''
        search_url = 'https://music.163.com/api/search/get/web?&s={}&type=1&offset={}&total=true&limit={}'
        keyword = re.sub(r'|[!@#$%^&*/]+', '', keyword)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res_json = (await client.post(
                    search_url.format(keyword, page, limit),
                    headers=NeteaseService._headers(),
                    cookies=self.cookies
                )).json()

            res_list = []
            if res_json["result"] == {} or res_json["code"] == 400 or res_json["result"]["songCount"] == 0:
                return res_list
            for data in res_json["result"]["songs"]:
                duration = data["duration"] // 1000
                artists_list = [info["name"] for info in data["artists"]]
                album_name = data.get('album', {}).get('name', '') if data.get('album') else ''
                res_list.append({
                    "idOrMd5": str(data["id"]),
                    "songName": data["name"],
                    "singer": ','.join(artists_list),
                    "album": album_name,
                    "duration": f'{duration // 60}:{duration % 60:02d}',
                })
            return res_list
        except Exception as e:
            logger.error(f'Failed to search song: {e}')
            return []

    @staticmethod
    def _merge_lyric_with_translation(lyric_text: str, tlyric_text: str) -> str:
        '''merge lyric with translation'''
        def parse_lyric_lines(text: str) -> tuple:
            lyric_dict = {}
            no_timestamp_lines = []
            timestamp_pattern = re.compile(r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)')
            for line in text.strip().split('\n'):
                line = line.strip()
                if not line:
                    continue
                match = timestamp_pattern.match(line)
                if match:
                    minutes = int(match.group(1))
                    seconds = int(match.group(2))
                    ms = int(match.group(3).ljust(3, '0')[:3])
                    timestamp = minutes * 60000 + seconds * 1000 + ms
                    lyric_content = match.group(4).strip()
                    if timestamp not in lyric_dict:
                        lyric_dict[timestamp] = {'original': '', 'translation': ''}
                    lyric_dict[timestamp]['original'] = lyric_content
                else:
                    no_timestamp_lines.append(line)
            return lyric_dict, no_timestamp_lines

        def format_timestamp(ms: int) -> str:
            return f'[{ms // 60000:02d}:{(ms % 60000) // 1000:02d}.{ms % 1000:03d}]'

        lyric_dict, lyric_no_timestamp_lines = parse_lyric_lines(lyric_text)
        tlyric_dict, _ = parse_lyric_lines(tlyric_text)

        for timestamp, content in tlyric_dict.items():
            if timestamp in lyric_dict and content['original']:
                lyric_dict[timestamp]['translation'] = content['original']

        result_lines = lyric_no_timestamp_lines[:]
        for timestamp in sorted(lyric_dict.keys()):
            content = lyric_dict[timestamp]
            if content['original']:
                result_lines.append(f"{format_timestamp(timestamp)} {content['original']}")
            if content['translation']:
                result_lines.append(f"{format_timestamp(timestamp)} {content['translation']}")
        
        return '\n'.join(result_lines)

    async def get_lyrics_by_song_id(self, song_id: str) -> str:
        '''
        get lyrics by song id
        Args:
            song_id: song id
        Returns:
            lyrics text
        '''
        lyrics_url = 'https://music.163.com/api/song/lyric?id={}&os=pc&lv=-1&kv=-1&tv=-1&rv=-1&yv=-1'
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res_json = (await client.get(
                    lyrics_url.format(song_id),
                    headers=NeteaseService._headers(),
                    cookies=self.cookies
                )).json()
            lyric_text = res_json.get('lrc', {}).get('lyric', '')
            tlyric_text = res_json.get('tlyric', {}).get('lyric', '')
            if lyric_text:
                return self._merge_lyric_with_translation(lyric_text, tlyric_text)
            return ''
        except Exception as e:
            logger.warning(f'Failed to get lyrics: {e}')
            return ''

    # =========== artist avatar =============
    async def search_artist(self, keyword: str, limit: int = 10) -> list[dict]:
        '''
        search artist by keyword
        Args:
            keyword: search keyword
            limit: max number of results to return
        Returns:
            list of artist info
        '''
        try:
            data = {'s': keyword, 'type': 100, 'limit': limit}
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    SEARCH_API,
                    data=data,
                    headers=NeteaseService._headers(),
                    cookies=self.cookies
                )
                response.raise_for_status()
                result = response.json()
                if result.get('code') != 200:
                    logger.warning(f'Failed to search artist: {result.get("msg")}')
                    return []
                results = []
                for item in result.get('result', {}).get('artists', []):
                    results.append({
                        'id': item['id'],
                        'name': item['name'],
                        'picUrl': item.get('picUrl', '') or item.get('img1v1Url', ''),
                    })
                return results
        except Exception as e:
            logger.error(f'Failed to search artist: {e}')
            return []

    async def get_artist_avatar_url(self, artist_name: str) -> str | None:
        '''
        get artist avatar url by artist name
        Args:
            artist_name: artist name
        Returns:
            artist avatar url or None if failed
        '''
        try:
            search_results = await self.search_artist(artist_name, limit=1)
            if search_results:
                pic_url = search_results[0].get('picUrl', '')
                if pic_url:
                    pic_url = pic_url.replace('http://', 'https://')
                    if '?' not in pic_url:
                        pic_url += '?param=300y300'
                    return pic_url
            return None
        except Exception as e:
            logger.error(f'Failed to get artist avatar url: {e}')
            return None

    async def download_artist_avatar(self, artist_name: str) -> bytes | None:
        '''
        download artist avatar by artist id
        Args:
            artist_id: artist id
        Returns:
            bytes of artist avatar or None if failed
        '''
        pic_url = self.get_artist_avatar_url(artist_name)
        if not pic_url:
            return None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(pic_url, headers=NeteaseService._headers(), cookies=self.cookies)
                response.raise_for_status()
                return response.content
        except Exception as e:
            logger.error(f'Failed to download artist avatar: {e}')
            return None

    # =========== song info ===========
    async def get_song_info(self, song_id: str) -> dict | None:
        '''
        get song info by song id

        When Netease triggers risk control or encounters special tracks (removed from stores/radio/cloud storage, etc.), 
        it may return a response without the "songs" field. 
        Here we perform defensive parsing and provide clear error messages 
        to prevent higher-level systems from receiving a bare "KeyError: 'songs'", 
        while also retrying once to account for occasional risk control issues. 
        If the song truly doesn't exist, return None so that higher-level systems can skip that candidate.
        '''
        song_info_url = 'https://music.163.com/api/song/detail/?id={}&ids=[{}]'

        songs = None
        last_desc = ''
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res_json = (await client.post(
                        song_info_url.format(song_id, song_id),
                        headers=NeteaseService._headers(),
                        cookies=self.cookies
                    )).json()
            except ValueError as exc:
                last_desc = f'Response is not valid JSON: {exc}'
                time.sleep(0.5)
                continue

            code = res_json.get('code')
            songs = res_json.get('songs')
            if songs:
                break
            if songs == []:
                return None
            
            last_desc = res_json.get('msg') or f'code={code}, keys={list(res_json.keys())}'
            if attempt == 0:
                time.sleep(0.6)
        
        if not songs:
            raise BusinessException(
                code=30525,
                msg=f'Failed to get song info: {last_desc}',
                status_code=502
            )

        song_json = songs[0]
        album = song_json.get('album', {})
        artist_list = [info['name'] for info in song_json.get('artists', [])]
        duration = song_json.get('duration', 0) // 1000

        pic_buffer = None
        pic_url = album.get('picUrl')
        if pic_url:
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    pic_response = await client.get(pic_url, headers=NeteaseService._headers(), cookies=self.cookies)
                    pic_response.raise_for_status()
                    with Image.open(BytesIO(pic_response.content)) as img:
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        img.thumbnail((512, 512))
                        pic_buffer = BytesIO()
                        img.save(pic_buffer, format='JPEG', quality=85)
                        pic_buffer.seek(0)
            except Exception as e:
                logger.warning(f'Failed to download song cover: {e}')
                pic_buffer = None

        lyric = await self.get_lyrics_by_song_id(song_id)
        publish_time = album.get('publishTime')
        year = (
            str(time.localtime(publish_time // 1000).tm_year)
            if publish_time else ''
        )

        return {
            'songName': song_json.get('name', ''),
            'singer': ','.join(artist_list),
            'album': album.get('name', ''),
            'duration': f'{duration // 60}:{duration % 60:02d}',
            'year': year,
            'trackNumber': (song_json.get('no'), album.get('size')),
            'lyric': lyric,
            'cover': pic_buffer,
        }
                
