# -*- encoding: utf-8 -*-
'''
@File      :   lyric_index_service.py
@Time      :   2025/11/01 11:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   lyric file index: lrc -> plain text -> tsvector, search snippets, daily line
'''


import asyncio
import re
from pathlib import Path

import aiofiles
from sqlalchemy import String, case, func, literal, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.core.deps import DbDep, SettingsDep
from app.core.logger import logger
from app.models import Lyric, Track

# regconfig rendered as a literal so that postgres does not see a varchar parameter
LYRIC_CFG = literal_column("'lyric_cfg'::regconfig")

# [mm:ss.xx] / [mm:ss:xx] time tags and <mm:ss.xx> enhanced (A2) tags
TIME_TAG = re.compile(r'\[\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?\]')
ENHANCED_TAG = re.compile(r'<\d{1,3}:\d{1,2}(?:[.:]\d{1,3})?>')
# [ti:...] [ar:...] [al:...] [by:...] [offset:...] [length:...] ...
META_TAG = re.compile(
    r'\[(?:ti|ar|al|by|offset|re|ve|length|kana|au|la|tool|encoding|total):[^\]]*\]',
    re.IGNORECASE,
)
# sentence boundaries used to trim snippet windows
SENTENCE_BREAKS = '\n。！？；，、!?;,'
# latin/digit word chars, used for the stem fallback of the jieba_stem dictionary
WORD_CHARS = re.compile(r'[0-9a-zA-Z_]')

# a lyric file that finally arrived can be extracted again: only the 'no_lyric'
# skip is re-armed, extract_failed keeps its terminal state for the next round.
REVIVE_BEST_STATUS = case((Lyric.best_note == 'no_lyric', 'pending'), else_=Lyric.best_status)
REVIVE_BEST_NOTE = case((Lyric.best_note == 'no_lyric', literal(None, String)), else_=Lyric.best_note)

MAX_SNIPPETS = 3
SNIPPET_WINDOW = 24
SNIPPET_MERGE_GAP = 8

# asyncpg rejects a statement with more than 32767 bind parameters. one lyric row
# takes 3 of them (track_id / path / status), so bulk inserts are chunked and a
# large library can no longer blow up the whole statement.
INSERT_BATCH = 2000
# the same cap applies to an IN (...) list, one parameter per element.
ID_BATCH = 5000


def to_plain(text: str) -> str:
    '''lrc text -> plain lyric text

    removes time tags, enhanced tags and metadata heads, keeps one lyric line
    per line and drops blank lines (they carry no search value).
    '''
    if not text:
        return ''
    lines = []
    for raw in text.splitlines():
        line = TIME_TAG.sub('', raw)
        line = ENHANCED_TAG.sub('', line)
        line = META_TAG.sub('', line).strip()
        if line:
            lines.append(line)
    return '\n'.join(lines)


def read_lyric_file(path: Path) -> str | None:
    '''read a lrc file, utf-8 first and gb18030 as fallback (common in cn lrc)'''
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding='gb18030')
        except (UnicodeDecodeError, OSError) as e:
            logger.warning(f'Read lyric failed, unsupported encoding: {path}: {e}')
            return None
    except OSError as e:
        logger.warning(f'Read lyric failed: {path}: {e}')
        return None


def _find_spans(text: str, term: str) -> list[tuple[int, int]]:
    '''all case-insensitive spans of term, with a prefix fallback for stemmed words'''
    if not term:
        return []
    lowered = text.lower()
    needle = term.lower()
    spans = []
    start = 0
    while True:
        idx = lowered.find(needle, start)
        if idx < 0:
            break
        spans.append((idx, idx + len(needle)))
        start = idx + len(needle)
    if spans:
        return spans
    # jieba_stem may cut a latin word ('loving' -> 'lov'), match its prefixes
    if WORD_CHARS.match(needle):
        for m in re.finditer(rf'{re.escape(needle)}[0-9a-zA-Z_]*', lowered):
            spans.append((m.start(), m.end()))
    return spans


def _expand(text: str, start: int, end: int, window: int) -> tuple[int, int]:
    '''grow a hit to a readable window, then trim it to a sentence boundary'''
    fs = max(0, start - window)
    fe = min(len(text), end + window)
    if fs > 0:
        cut = max(text.rfind(ch, max(0, fs - 10), fs + 1) for ch in SENTENCE_BREAKS)
        if cut >= 0:
            fs = cut + 1
    if fe < len(text):
        cut = -1
        for ch in SENTENCE_BREAKS:
            idx = text.find(ch, fe - 1, min(len(text), fe + 10))
            if idx >= 0 and (cut < 0 or idx < cut):
                cut = idx
        if cut >= 0:
            fe = cut
    return max(0, min(fs, start)), min(len(text), max(fe, end))


def build_snippets(text: str, terms: list[str], max_snippets: int = MAX_SNIPPETS,
                   window: int = SNIPPET_WINDOW, merge_gap: int = SNIPPET_MERGE_GAP) -> list[dict]:
    '''build highlighted snippets of a lyric text

    a query term may appear several times in the same lyric: every hit inside a
    snippet is highlighted, and snippets whose windows overlap (or are closer
    than merge_gap) are merged into one.
    '''
    if not text or not terms:
        return []

    spans: list[tuple[int, int]] = []
    for term in terms:
        spans.extend(_find_spans(text, term))
    if not spans:
        return []
    spans.sort()

    # 1. merge overlapping / adjacent hits into groups
    groups: list[list[int]] = []
    for start, end in spans:
        if groups and start <= groups[-1][1] + merge_gap:
            groups[-1][1] = max(groups[-1][1], end)
        else:
            groups.append([start, end])

    # 2. expand each group to a window, then merge overlapping windows
    fragments: list[list[int]] = []
    for start, end in groups:
        fs, fe = _expand(text, start, end, window)
        if fragments and fs <= fragments[-1][1] + merge_gap:
            fragments[-1][1] = max(fragments[-1][1], fe)
        else:
            fragments.append([fs, fe])

    # 3. keep the densest snippets, then restore reading order
    if len(fragments) > max_snippets:
        density = [(sum(1 for s, e in spans if fs <= s < fe), fs, fe) for fs, fe in fragments]
        density.sort(key=lambda x: (-x[0], x[1]))
        fragments = sorted([[fs, fe] for _, fs, fe in density[:max_snippets]])

    snippets = []
    for fs, fe in fragments:
        highlights = [[max(s, fs) - fs, min(e, fe) - fs] for s, e in spans if fs <= s < fe]
        snippets.append({'text': text[fs:fe], 'highlights': highlights})
    return snippets


class LyricIndexService:
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    # region backend use
    def lrc_abs_path(self, lyric_path: str | Path) -> Path:
        p = Path(lyric_path)
        return p if p.is_absolute() else self.settings.MUSIC_LIBRARY_PATH / p

    def track_lrc_path(self, track_path: str) -> str:
        '''track path -> lyric path, same format as tracks.path, only the suffix changes'''
        return str(Path(track_path).with_suffix('.lrc'))

    async def ensure_row(self, track_id: int, track_path: str) -> bool:
        '''make sure a lyric row exists for the track, returns True when created'''
        stmt = (
            pg_insert(Lyric)
            .values(track_id=track_id, path=self.track_lrc_path(track_path), status='pending')
            .on_conflict_do_nothing(index_elements=['track_id'])
            .returning(Lyric.id)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None

    async def ensure_row_by_track_path(self, track_path: str) -> int | None:
        '''ensure the lyric row of a track exists, returns the track id'''
        track_id = (await self.db.execute(
            select(Track.id).where(Track.path == track_path)
        )).scalar_one_or_none()
        if track_id is None:
            return None
        await self.ensure_row(track_id, track_path)
        return track_id

    async def align_rows(self) -> int:
        '''make the lyric table match tracks: one pending row per live track

        idempotent, existing rows are never touched. returns the number of rows
        created (0 on a second call).
        '''
        tracks = (await self.db.execute(
            select(Track.id, Track.path).where(Track.is_deleted.is_(False))
        )).all()
        existing = set((await self.db.execute(select(Lyric.track_id))).scalars())
        payload = [
            {'track_id': tid, 'path': self.track_lrc_path(path), 'status': 'pending'}
            for tid, path in tracks if tid not in existing
        ]
        for start in range(0, len(payload), INSERT_BATCH):
            await self.db.execute(
                pg_insert(Lyric)
                .values(payload[start:start + INSERT_BATCH])
                .on_conflict_do_nothing(index_elements=['track_id'])
            )
        return len(payload)

    async def sync_file_state(self, lyric_id: int, lyric_path: str) -> str:
        '''refresh one row from the disk: file exists -> ok + indexed, else pending

        returns the resulting status so that a batch caller can report progress.
        '''
        lrc_path = self.lrc_abs_path(lyric_path)
        if not lrc_path.exists():
            # no file: back to pending, but never revive a terminal state
            # (skip / review / failed keep their fetch result for the next round)
            await self.db.execute(
                update(Lyric)
                .where(Lyric.id == lyric_id)
                .values(
                    status=case((Lyric.status.in_(('ok', 'pending')), 'pending'), else_=Lyric.status),
                    written=False,
                    written_at=None,
                    lyric_plain=None,
                    lyric_tsv=None,
                )
            )
            return 'pending'

        raw = read_lyric_file(lrc_path)
        plain = to_plain(raw or '')
        await self.db.execute(
            update(Lyric)
            .where(Lyric.id == lyric_id)
            .values(
                status='ok',
                written=True,
                written_at=func.now(),
                lyric_plain=plain or None,
                lyric_tsv=func.to_tsvector(LYRIC_CFG, plain) if plain else None,
                best_status=REVIVE_BEST_STATUS,
                best_note=REVIVE_BEST_NOTE,
            )
        )
        return 'ok'

    async def sync_track(self, track_id: int) -> str | None:
        '''(re)sync the lyric file of a track by id, used by watcher and imports'''
        lyric = (await self.db.execute(
            select(Lyric).where(Lyric.track_id == track_id)
        )).scalar_one_or_none()
        if not lyric:
            return None
        return await self.sync_file_state(lyric.id, lyric.path)

    async def mark_absent(self, lyric: Lyric) -> None:
        '''the lyric file is gone: keep the fetch record, drop the indexed content'''
        lyric.written = False
        lyric.written_at = None
        lyric.lyric_plain = None
        lyric.lyric_tsv = None
        lyric.best = None
        lyric.best_status = 'skip'
        lyric.best_note = 'no_lyric'
        # an exported stamp of an older round must not leak into the next one
        lyric.best_exported_at = None
        if lyric.status == 'ok':
            lyric.status = 'pending'

    async def status_counts(self) -> dict:
        '''row counts grouped by status and best_status, for the admin dashboard'''
        rows = (await self.db.execute(
            select(Lyric.status, func.count()).group_by(Lyric.status)
        )).all()
        best_rows = (await self.db.execute(
            select(Lyric.best_status, func.count()).group_by(Lyric.best_status)
        )).all()
        written = (await self.db.execute(
            select(func.count()).select_from(Lyric).where(Lyric.written.is_(True))
        )).scalar_one()
        return {
            'status': {s: c for s, c in rows},
            'best_status': {s: c for s, c in best_rows},
            'written': written,
        }
    # endregion

    def library_relative_lrc(self, audio_path: str) -> str:
        '''watcher audio path (absolute or relative) -> posix relative lrc path'''
        root = Path(self.settings.MUSIC_LIBRARY_PATH)
        path = Path(audio_path)
        try:
            rel = path.relative_to(root)
        except ValueError:
            try:
                rel = path.resolve().relative_to(root.resolve())
            except (ValueError, OSError):
                rel = path
        return rel.with_suffix('.lrc').as_posix()

    async def apply_fetch_result(self, result) -> bool:
        '''write a LyricResult back into the lyric table

        the fetch fields come from the result, written / plain / tsv always come
        from the disk, so a file deleted by hand can never stay "searchable".
        '''
        target = self.library_relative_lrc(result.path)
        lyric = (await self.db.execute(
            select(Lyric).where(func.replace(Lyric.path, '\\', '/') == target)
        )).scalar_one_or_none()
        if not lyric:
            logger.debug(f'🎵No lyric row for fetched track, skipped: {target}')
            return False

        lrc_path = Path(result.lrc_path) if result.lrc_path else self.lrc_abs_path(lyric.path)
        status = result.status
        note = result.note or None
        if await asyncio.to_thread(lrc_path.exists):
            raw = await asyncio.to_thread(read_lyric_file, lrc_path)
            plain = to_plain(raw or '')
            values = {
                'written': True,
                'written_at': func.now(),
                'lyric_plain': plain or None,
                'lyric_tsv': func.to_tsvector(LYRIC_CFG, plain) if plain else None,
                'best_status': REVIVE_BEST_STATUS,
                'best_note': REVIVE_BEST_NOTE,
            }
        else:
            if status == 'ok':
                status, note = 'failed', (f'{note}|' if note else '') + 'file_missing'
            values = {'written': False, 'written_at': None,
                      'lyric_plain': None, 'lyric_tsv': None}

        values.update(
            status=status,
            score=result.score,
            dur_delta=result.dur_delta,
            source=result.source or None,
            source_id=result.source_id or None,
            fetch_note=note,
        )
        await self.db.execute(update(Lyric).where(Lyric.id == lyric.id).values(**values))
        return True

    async def fetch_candidates(self, limit: int = 500) -> list[dict]:
        '''tracks still waiting for a lyric (pending / failed), submits them to the fetcher'''
        tracks = (await self.db.execute(
            select(Track)
            .join(Lyric, Lyric.track_id == Track.id)
            .where(Lyric.status.in_(('pending', 'failed')), Track.is_deleted.is_(False))
            .order_by(Lyric.id)
            .limit(limit)
            .options(selectinload(Track.artists), selectinload(Track.album))
        )).scalars().all()
        return [{
            'path': str(Path(self.settings.MUSIC_LIBRARY_PATH) / t.path),
            'title': t.title,
            'artists': [a.name for a in t.artists],
            'album': t.album.title if t.album else '',
            'duration': float(t.duration or 0),
        } for t in tracks]

    # region search
    async def search(self, keyword: str, limit: int = 20, offset: int = 0) -> tuple[int, list[dict]]:
        '''full text search over indexed lyrics, returns (total, items)'''
        keyword = (keyword or '').strip()
        if not keyword:
            return 0, []

        query = func.websearch_to_tsquery(LYRIC_CFG, keyword)
        condition = Lyric.lyric_tsv.op('@@')(query)

        base = (
            select(Lyric, Track)
            .join(Track, Track.id == Lyric.track_id)
            .where(condition, Lyric.written.is_(True), Track.is_deleted.is_(False))
        )

        total = (await self.db.execute(
            select(func.count()).select_from(base.subquery())
        )).scalar_one()

        if not total:
            return 0, []

        # lexemes are needed by the application side highlighter
        terms = (await self.db.execute(
            select(func.array_to_string(func.tsvector_to_array(func.to_tsvector(LYRIC_CFG, keyword)), '|'))
        )).scalar_one()
        terms = [t for t in (terms or '').split('|') if t]

        rows = (await self.db.execute(
            base.options(
                selectinload(Track.artists),
                selectinload(Track.album),
            )
            .order_by(func.ts_rank(Lyric.lyric_tsv, query).desc(), Lyric.id)
            .limit(limit)
            .offset(offset)
        )).all()

        items = []
        for lyric, track in rows:
            items.append({
                'lyric_id': lyric.id,
                'track_id': track.id,
                'title': track.title,
                'artists': [a.name for a in track.artists],
                'album': track.album.title if track.album else None,
                'cover_art_hash': track.cover_art_hash,
                'duration': track.duration,
                'snippets': build_snippets(lyric.lyric_plain or '', terms),
            })
        return total, items
    # endregion

    # region daily line
    async def daily_line(self) -> dict | None:
        '''random best line, the persistence of "one per day" is done by the client'''
        row = (await self.db.execute(
            select(Lyric, Track)
            .join(Track, Track.id == Lyric.track_id)
            .where(
                Lyric.best_status == 'extracted',
                Lyric.best.is_not(None),
                Lyric.best != '',
                Track.is_deleted.is_(False),
            )
            .order_by(func.random())
            .limit(1)
            .options(
                selectinload(Track.artists),
                selectinload(Track.album),
            )
        )).first()
        if not row:
            return None
        lyric, track = row
        return {
            'lyric_id': lyric.id,
            'track_id': track.id,
            'best': lyric.best,
            'title': track.title,
            'artists': [a.name for a in track.artists],
            'album': track.album.title if track.album else None,
            'cover_art_hash': track.cover_art_hash,
            'duration': track.duration,
            'path': lyric.path,
        }
    # endregion
