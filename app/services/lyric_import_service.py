# -*- encoding: utf-8 -*-
'''
@File      :   lyric_import_service.py
@Time      :   2025/11/01 13:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   import external lyric results: fetch result csv (from the sqlite tool) and best line json
'''


import asyncio
import csv
import io
import json
from pathlib import Path

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.core.deps import DbDep, SettingsDep
from app.core.logger import logger
from app.models import Lyric, Track
from app.services.lyric_index_service import ID_BATCH, LYRIC_CFG, read_lyric_file, to_plain

VALID_STATUS = ('pending', 'ok', 'review', 'skip', 'failed')
COMMIT_EVERY = 100


def _decode(content: bytes) -> str:
    '''csv/json from the external tool is utf-8 (with or without BOM), gb18030 as fallback'''
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode('utf-8', errors='replace')


def _posix(path: str) -> str:
    '''normalize a library relative path so that windows and unix sqlite dumps match'''
    return Path(path.replace('\\', '/')).as_posix()


def to_lrc_path(track_path: str) -> str:
    '''the sqlite dump stores the audio path, the lyric path only differs by the suffix'''
    return _posix(str(Path(track_path).with_suffix('.lrc')))


def _to_float(value) -> float | None:
    try:
        if value is None or value == '':
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class LyricImportService:
    def __init__(self, db: DbDep, settings: SettingsDep):
        self.db = db
        self.settings = settings

    async def _load_index(self) -> dict[str, tuple[int, str, bool]]:
        '''posix path -> (lyric_id, path, written)'''
        rows = (await self.db.execute(select(Lyric.id, Lyric.path, Lyric.written))).all()
        return {_posix(path): (lyric_id, path, written) for lyric_id, path, written in rows}

    def _abs_path(self, lyric_path: str) -> Path:
        p = Path(lyric_path)
        return p if p.is_absolute() else self.settings.MUSIC_LIBRARY_PATH / p

    async def _read_plain(self, lyric_path: str) -> tuple[bool, str | None]:
        '''(file exists, plain text); file IO runs in a thread to keep the loop free'''
        path = self._abs_path(lyric_path)
        if not await asyncio.to_thread(path.exists):
            return False, None
        raw = await asyncio.to_thread(read_lyric_file, path)
        return True, to_plain(raw or '')

    async def import_fetch_csv(self, content: bytes) -> dict:
        '''
        import the fetch result exported from the external sqlite database.

        columns: path,title,artist,album,status,conf,score,dur_delta,source,source_id,note,cand
        written / lyric_plain / lyric_tsv always come from the disk, never from the dump.
        '''
        reader = csv.DictReader(io.StringIO(_decode(content)))
        index = await self._load_index()

        stats = {'rows': 0, 'matched': 0, 'updated': 0, 'unmatched': 0,
                 'written': 0, 'invalid_status': 0}

        for row in reader:
            stats['rows'] += 1
            path = (row.get('path') or '').strip()
            if not path:
                continue
            hit = index.get(to_lrc_path(path))
            if not hit:
                stats['unmatched'] += 1
                continue
            stats['matched'] += 1
            lyric_id, lyric_path, _ = hit

            status = (row.get('status') or '').strip().lower()
            if status not in VALID_STATUS:
                stats['invalid_status'] += 1
                status = 'failed'

            exists, plain = await self._read_plain(lyric_path)
            values = {
                'status': status,
                'score': _to_float(row.get('score')),
                'dur_delta': _to_float(row.get('dur_delta')),
                'source': (row.get('source') or '').strip() or None,
                'source_id': (row.get('source_id') or '').strip() or None,
                'fetch_note': (row.get('note') or '').strip() or None,
                'written': exists,
                'written_at': func.now() if exists else None,
                'lyric_plain': (plain or None) if exists else None,
                'lyric_tsv': func.to_tsvector(LYRIC_CFG, plain) if (exists and plain) else None,
            }
            await self.db.execute(update(Lyric).where(Lyric.id == lyric_id).values(**values))
            stats['updated'] += 1
            if exists:
                stats['written'] += 1
            if stats['updated'] % COMMIT_EVERY == 0:
                await self.db.commit()

        await self.db.commit()
        logger.info(f'🎵Lyric fetch result imported: {stats}')
        return stats

    async def export_best_json(self, limit: int | None = None) -> list[dict]:
        '''
        export the rows still waiting for a best line, for the external extractor.

        every exported row is stamped with best_exported_at, which is what lets
        the import finalize exactly this round: rows that turn pending after the
        export carry no stamp and are never touched by the import.
        '''
        stmt = (
            select(Lyric, Track)
            .join(Track, Track.id == Lyric.track_id)
            .where(Lyric.best_status == 'pending', Track.is_deleted.is_(False))
            .order_by(Lyric.id)
            .options(selectinload(Track.artists), selectinload(Track.album))
        )
        if limit:
            stmt = stmt.limit(limit)
        rows = (await self.db.execute(stmt)).all()
        if not rows:
            return []

        items = [{
            'path': lyric.path,
            'title': track.title,
            'artists': [a.name for a in track.artists],
            'album': track.album.title if track.album else None,
            'duration': float(track.duration or 0),
            'lyric': lyric.lyric_plain or '',
        } for lyric, track in rows]

        ids = [lyric.id for lyric, _ in rows]
        for start in range(0, len(ids), ID_BATCH):
            await self.db.execute(
                update(Lyric)
                .where(Lyric.id.in_(ids[start:start + ID_BATCH]))
                .values(best_exported_at=func.now())
            )
        await self.db.commit()
        logger.info(f'🎵Lyric best export: {len(items)} pending row(s) exported.')
        return items

    async def import_best_json(self, content: bytes) -> dict:
        '''
        import the best line json: [{"path": "...lrc", "best": "..."}]

        matched rows are marked extracted. a row is only finalized (skip with a
        reason) when it belongs to an export round (best_exported_at is set) and
        is still pending afterwards: the extractor returned nothing for it. rows
        already extracted / skip, and rows that turned pending after the export,
        keep their state.
        '''
        try:
            data = json.loads(_decode(content))
        except json.JSONDecodeError as e:
            raise ValueError(f'invalid json: {e}') from e
        if not isinstance(data, list):
            raise ValueError('best json must be a list of {"path", "best"} objects')

        index = await self._load_index()
        stats = {'rows': len(data), 'matched': 0, 'unmatched': 0, 'extracted': 0,
                 'skip': 0, 'no_lyric': 0, 'extract_failed': 0}

        for item in data:
            if not isinstance(item, dict):
                continue
            path = (item.get('path') or '').strip()
            best = (item.get('best') or '').strip()
            if not path or not best:
                continue
            hit = index.get(_posix(path))
            if not hit:
                stats['unmatched'] += 1
                continue
            stats['matched'] += 1
            lyric_id = hit[0]
            # skip is terminal, an old dump must not revive it
            updated = (await self.db.execute(
                update(Lyric)
                .where(Lyric.id == lyric_id, Lyric.best_status.in_(('pending', 'extracted')))
                .values(best=best[:200], best_status='extracted', best_note=None,
                        best_exported_at=None)
                .returning(Lyric.id)
            )).all()
            if updated:
                stats['extracted'] += 1

        # leftovers of the export round: nothing came back for them, they are terminal.
        # returning the ids instead of reading rowcount keeps the result typed.
        exported = (Lyric.best_status == 'pending', Lyric.best_exported_at.is_not(None))
        no_lyric = (await self.db.execute(
            update(Lyric)
            .where(*exported, Lyric.written.is_(False))
            .values(best_status='skip', best_note='no_lyric', best_exported_at=None)
            .returning(Lyric.id)
        )).all()
        failed = (await self.db.execute(
            update(Lyric)
            .where(*exported, Lyric.written.is_(True))
            .values(best_status='skip', best_note='extract_failed', best_exported_at=None)
            .returning(Lyric.id)
        )).all()
        stats['no_lyric'] = len(no_lyric)
        stats['extract_failed'] = len(failed)
        stats['skip'] = len(no_lyric) + len(failed)

        await self.db.commit()
        logger.info(f'🎵Lyric best json imported: {stats}')
        return stats
