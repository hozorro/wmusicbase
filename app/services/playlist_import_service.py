# -*- encoding: utf-8 -*-
'''
@File      :   playlist_import_service.py
@Desc      :   match imported playlist tracks and create a playlist from picked ids
'''


from fastapi import Request, status
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload, joinedload, load_only
from sqlalchemy.exc import IntegrityError
from app.core.deps import DbDep
from app.core.exceptions import BusinessException
from app.core.logger import logger
from app.models import Track, Artist, Album, Playlist, PlaylistTrack
from app.schemas.playlist_import import (
    MatchLevel,
    PlaylistImportTrack,
    PlaylistMatchCandidate,
    PlaylistTrackMatchResult,
    PlaylistMatchResponse,
    PlaylistCreateFromMatchRequest,
    PlaylistCreateFromMatchResponse,
)

CANDIDATE_LIMIT = 5


class PlaylistImportService:
    '''imported-playlist matching and creation, independent from netease/legacy services'''

    def __init__(self, db: DbDep, request: Request):
        self.db = db
        self.current_user_id = request.state.user_id

    @staticmethod
    def _to_candidate(track: Track, level: MatchLevel) -> PlaylistMatchCandidate:
        return PlaylistMatchCandidate(
            track_id=track.id,
            title=track.title,
            artists=[a.name for a in track.artists],
            album=track.album.title if track.album else '',
            path=track.path,
            match_level=level,
        )

    @staticmethod
    def _track_options(stmt):
        '''eager load only the fields needed to render a candidate'''
        return stmt.options(
            load_only(Track.id, Track.title, Track.path, Track.album_id),
            selectinload(Track.artists).load_only(Artist.id, Artist.name),
            joinedload(Track.album).load_only(Album.id, Album.title),
        )

    async def _load_tracks_by_paths(self, tracks: list[PlaylistImportTrack]) -> dict[str, Track]:
        '''one batched IN query for every path in the input'''
        unique_paths = list(dict.fromkeys(t.path for t in tracks if t.path))
        if not unique_paths:
            return {}
        stmt = self._track_options(
            select(Track).where(Track.path.in_(unique_paths), Track.is_deleted == False)
        )
        result = await self.db.execute(stmt)
        return {track.path: track for track in result.scalars().unique().all()}

    async def _search_tracks(
        self,
        title: str,
        artist_names: list[str] | None,
        album_title: str | None,
        exact: bool,
        limit: int,
        level: MatchLevel,
    ) -> list[PlaylistMatchCandidate]:
        '''search local tracks with title / artist / album filters'''
        stmt = select(Track).where(Track.is_deleted == False)

        if exact:
            stmt = stmt.where(func.lower(Track.title) == title.lower())
        else:
            stmt = stmt.where(Track.title.ilike(f'%{title}%'))

        if artist_names:
            stmt = stmt.join(Track.artists)
            conditions = [
                func.lower(Artist.name) == name.lower() if exact
                else Artist.name.ilike(f'%{name}%')
                for name in artist_names
            ]
            stmt = stmt.where(or_(*conditions))

        if album_title:
            stmt = stmt.join(Track.album).where(
                func.lower(Album.title) == album_title.lower() if exact
                else Album.title.ilike(f'%{album_title}%')
            )

        result = await self.db.execute(self._track_options(stmt.limit(limit)))
        return [self._to_candidate(t, level) for t in result.scalars().unique().all()]

    async def _find_meta_candidates(self, item: PlaylistImportTrack) -> list[PlaylistMatchCandidate]:
        '''three-level strategy: exact > title+artist > title only'''
        title = (item.title or '').strip()
        if not title:
            return []
        artists = [a.strip() for a in item.artists if a and a.strip()]
        album = (item.album or '').strip()

        candidates: list[PlaylistMatchCandidate] = []
        seen: set[int] = set()

        strategies: list[tuple[list[str] | None, str | None, bool, MatchLevel]] = []
        if artists and album:
            strategies.append((artists, album, True, 'exact'))
        if artists:
            strategies.append((artists, None, False, 'artist'))
        strategies.append((None, None, False, 'title'))

        for artist_names, album_title, exact, level in strategies:
            remaining = CANDIDATE_LIMIT - len(candidates)
            if remaining <= 0:
                break
            found = await self._search_tracks(title, artist_names, album_title, exact, remaining, level)
            for candidate in found:
                if candidate.track_id not in seen:
                    candidates.append(candidate)
                    seen.add(candidate.track_id)
        return candidates

    async def match_tracks(self, tracks: list[PlaylistImportTrack]) -> PlaylistMatchResponse:
        '''match each input track by path (priority) or by title/artists/album'''
        path_map = await self._load_tracks_by_paths(tracks)
        results: list[PlaylistTrackMatchResult] = []

        for index, item in enumerate(tracks):
            if item.path:
                # path wins: all other fields of this track are ignored
                track = path_map.get(item.path)
                candidates = [self._to_candidate(track, 'path')] if track else []
                match_by = 'path' if candidates else 'none'
            else:
                candidates = await self._find_meta_candidates(item)
                match_by = 'meta' if candidates else 'none'
            results.append(PlaylistTrackMatchResult(
                index=index,
                source=item,
                match_by=match_by,
                candidates=candidates,
            ))

        matched_count = sum(1 for r in results if r.candidates)
        logger.info(
            f'playlist json match finished: total={len(tracks)}, '
            f'matched={matched_count}, unmatched={len(tracks) - matched_count}'
        )
        return PlaylistMatchResponse(
            total=len(tracks),
            matched_count=matched_count,
            unmatched_count=len(tracks) - matched_count,
            results=results,
        )

    async def create_playlist_from_track_ids(
        self, data: PlaylistCreateFromMatchRequest
    ) -> PlaylistCreateFromMatchResponse:
        '''create a playlist from picked track ids, keeping the submitted order'''
        title = data.title.strip()
        if not title:
            raise BusinessException(
                code=70508,
                msg='playlist title must not be blank',
                detail={'title': data.title},
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

        # deduplicate without losing the order of the match result
        ordered_ids = list(dict.fromkeys(data.track_ids))
        valid_ids: list[int] = []
        if ordered_ids:
            result = await self.db.execute(
                select(Track.id).where(Track.id.in_(ordered_ids), Track.is_deleted == False)
            )
            existing_ids = set(result.scalars().all())
            valid_ids = [tid for tid in ordered_ids if tid in existing_ids]

        playlist = Playlist(
            title=title,
            comment=data.comment,
            user_id=self.current_user_id,
        )
        try:
            self.db.add(playlist)
            await self.db.flush()
            if valid_ids:
                self.db.add_all([
                    PlaylistTrack(playlist_id=playlist.id, track_id=tid, position=index)
                    for index, tid in enumerate(valid_ids)
                ])
            await self.db.commit()
            await self.db.refresh(playlist)
        except IntegrityError as e:
            await self.db.rollback()
            raise BusinessException(
                code=70509,
                msg=f'fail to create playlist with integrity error: {title}',
                detail={'error': str(e)},
                status_code=status.HTTP_409_CONFLICT,
            )
        except Exception as e:
            await self.db.rollback()
            logger.exception(f'fail to create playlist from matched ids: {e}')
            raise BusinessException(
                code=70510,
                msg=f'fail to create playlist with unknown error: {title}',
                detail={'error': str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        requested = len(data.track_ids)
        ignored = requested - len(valid_ids)
        detail = (
            f'playlist created: id={playlist.id}, title={playlist.title}, '
            f'added={len(valid_ids)}, ignored={ignored} '
            f'(unmatched, duplicated, deleted or not found)'
        )
        logger.info(f'playlist json create finished: {detail}')
        return PlaylistCreateFromMatchResponse(
            id=playlist.id,
            title=playlist.title,
            requested=requested,
            added=len(valid_ids),
            ignored=ignored,
            detail=detail,
        )
