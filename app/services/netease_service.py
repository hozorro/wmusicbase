# -*- encoding: utf-8 -*-
'''
@File      :   netease_service.py
@Time      :   2025/01/01 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   netease playlist import service
'''


from this import d

import httpx
from pathlib import Path
from sqlalchemy import select, or_, and_, func
from sqlalchemy.orm import selectinload, joinedload, load_only
from app.core.deps import SettingsDep, DbDep
from app.core.exceptions import BusinessException
from app.core.logger import logger
from app.models import Track, Artist, Album, Playlist, PlaylistTrack
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
cookies = {
    '_iuqxldmzr_': '32', 
    '_ntes_nuid': 'b374451bc0d9b0ec930f5c49e1d2b580', 
    'WEVNSM': '1.0.0', 
    'WM_TID': 'S7Y7kKyLypxFREVVAQKSAs%2FyFAVNdenu', 
    'ntes_utid': 'tid._.ksN07W%252BoT2hBRlUUAFbXA5%252F3BVBIbRgx._.0', 
    '_ntes_nnid': 'b374451bc0d9b0ec930f5c49e1d2b580,1758941281373', 
    '__snaker__id': 'RTkMng4YCAfClhXt', 
    'NMTID': '00O73bUcJ2i14yYVknuhHIeQzW_b5cAAAGgj6LbvA', 
    'WNMCID': 'wmhram.1789116211946.01.0', 
    'sDeviceId': 'YD-aQgevZVspqZBQ0RUUBeSUou3BAUNaF18', 
    'gdxidpyhxdE': '3V%2FL3%2BDe%2B21QxEebVL5D7eNL4Anu8AogqOqufWKnEh%5CmWJH7G7EZ0gG65HexG4XlDO0GLRAW1pS1NPcEwGDOC%2Frtm1TSOzDVGm359k9SE1Tug%2F0aosbN8r0bTWO%5Cl61etTMbCviVxMkOVyE2RWvwLx8s%2BSLTZyigsPXKp716bj%2BwKcPe%3A1789117116345', 
    '__csrf': '272d719232e7fb0d355491a732e0c203', 
    'MUSIC_U': '00641C69348F0E0E4622B340A37AD7A078C203FD69443995BD2ADC228034C76E5ACD0A9CAFF5C87D1C68556A5A9B29D432566ADE60751CC6E62FA314033A37C53D1DB948C727BA202426F16D9C59CE8096FF99F54141D414D271E80407BF2D50E951E355296F776AF5C3610109232A50284FD3CA4CD5BBF5E108D5232DA45874E9EA0EB80D384D09E82097E4750F34551E34C888C17011B8E22A1472E3D7FEC5A44E25EDFD40FC7EFB46B470869717C81D8C0488AAE1D6FDDBA3871DFD8829227198C69E19B1AA32E199F8C4EFDF259DA3B478D27C28D7872CA03FCE92CDA410BB888A7258EA4490B2016D48AAB8011ECFF08D01936A843CDD805F93B2B6E405409D96AEF5ACD1B07A97805B57AA38560EF4A227641495D12407683179F43A6E5F0D9391507EA58C0C588FBF3EBA6CF9AC5169270FF72731C7BD67893631A9C886EAFE931B0C7DDF87A2302C4644F7781B27F3523A1C95ADAC93F71206FC45CC2C5480833F3FC5432D10C9E6B5F6C94FA9E61A772ADBCECFCCABA47C70CB021AE6D4B23B28A742F8F7FA058654114E2B9D8F7C29612E8303458941BA2D58DDBCB5', 
    'ntes_kaola_ad': '1', 
    'WM_NI': '3hIsmZjPlTqen%2B6UUwOZak%2F3brNTaueCbzvirgTInV7wS4yjFZnhpV6M3OzQceuFprdRfZKZNWw0lhF1Lx8xH7uhQsX8Sv7mIgMe5Gsz4lQsyWCp%2FCFyBNVsdguK6Fu5NWc%3D', 
    'WM_NIKE': '9ca17ae2e6ffcda170e2e6eed1c67fa88dbc92b621b8eb8ea7c14a928a9fb0c95a8f94869be87fb486e1d4db2af0fea7c3b92af1b88794f052aa90a4b5f46faef5fab6d87d8d86af8cae39a2ae82b5e47fa79dae9bf563b2b99caaed5ef5a99dd5fc628686a289f35ef693fdb0f95ba1bbbba7f37aa88eaabbca528e89b9d1ef6486ef8499bb748ce9bb89d4799ce89d97b6678bb98386b84db1a6fc8dd479bb898d91ae4986a78eafd579a8b9bbacb54eb7eb82b8e237e2a3', 
    'JSESSIONID-WYYY': 'wrWeXd4arHeFJWDAG%5CQIHMDPdxy1y3Osztiuus4fOXd5m1NCVP5rNdsVRSG0sNg%5CsimUWpYaQ7JQMfjGDl%2BSXgh09f0pz7ruMe2%2FU%5CZF%5Ca2ZIMeS5pTH3CEP1TmGNR29BQi1XtR7%2FGzBdfek8pQNX%5CWhaPssgM6stDbodti%2B9pjDbDtO%3A1789357472417', 
    'Hm_lvt_1483fb4774c02a30ffa6f0e2945e9b70': '1789116211,1789209365,1789301614,1789355673', 
    'HMACCOUNT': '1063F49E9A872DB5', 
    'Hm_lpvt_1483fb4774c02a30ffa6f0e2945e9b70': '1789355675'
}


class NeteaseService:
    '''netease playlist import service'''

    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings
        self.api_base = 'https://music.163.com/api/v6/playlist/detail'

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
                # response = await client.get(url)
                headers = {
                    'User-Agent': USER_AGENT,
                    'Referer': REFERER,
                    'Accept': '*/*',
                }
                request_cookies = DEFAULT_COOKIES.copy()
                request_cookies.update(cookies)
                response = await client.post(self.api_base, data={'id': playlist_id}, cookies=request_cookies)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f'Netease API HTTP error: {e.response.status_code} for playlist {playlist_id}')
            raise BusinessException(
                code=30601,
                msg=f'netease api request failed: {e.response.status_code}',
                status_code=502
            )
        except httpx.RequestError as e:
            logger.error(f'Netease API request error: {e} for playlist {playlist_id}')
            raise BusinessException(
                code=30602,
                msg='netease api request failed: network error',
                status_code=502
            )
        except Exception as e:
            logger.error(f'Netease API unexpected error: {e} for playlist {playlist_id}')
            raise BusinessException(
                code=30603,
                msg='netease api request failed: unknown error',
                status_code=502
            )

        # check response code
        if data.get('code') != 200:
            logger.warning(f'Netease playlist {playlist_id} not found or error: {data}')
            raise BusinessException(
                code=30604,
                msg='playlist not found on netease',
                status_code=404
            )

        playlist_data = data.get('playlist', {})
        if not playlist_data:
            raise BusinessException(
                code=30604,
                msg='playlist not found on netease',
                status_code=404
            )

        # parse tracks
        tracks = []
        for track_data in playlist_data.get('tracks', []):
            # parse artists
            artists = [ar.get('name', '') for ar in track_data.get('ar', [])]
            # parse album
            album = track_data.get('al', {}).get('name', '')
            # parse duration
            duration = track_data.get('dt', 0)
            # parse mainTitle (use name as fallback if mainTitle is empty)
            main_title = track_data.get('mainTitle')
            if main_title and main_title.strip():
                main_title = main_title.strip()
            else:
                main_title = None

            tracks.append(NeteaseTrackInfo(
                id=track_data.get('id', 0),
                name=track_data.get('name', ''),
                mainTitle=main_title,
                artists=artists,
                album=album,
                duration=duration
            ))

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
