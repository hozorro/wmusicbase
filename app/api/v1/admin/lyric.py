# -*- encoding: utf-8 -*-
'''
@File      :   lyric.py
@Time      :   2025/11/01 12:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router lyric: lyric table maintenance (init / export / import / status)
'''


import asyncio
import json
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.background.watcher_manager import watcher
from app.core.config import settings
from app.core.db import AsyncSessionLocal
from app.core.deps import DbDep, require_admin
from app.core.exceptions import BusinessException
from app.core.logger import logger
from app.core.state import system_state
from app.models import Lyric
from app.schemas.common import ResponseModel
from app.schemas.user import CurrentUser
from app.services.lyric_import_service import LyricImportService
from app.services.lyric_index_service import LyricIndexService

router = APIRouter()

BATCH_SIZE = 100
# one fetcher per process: the incremental endpoint reuses the watcher worker
lyric_service = watcher.lyric_service


async def run_lyric_init_task():
    '''
    align the lyric table with tracks and index every lyric file on disk.
    one row per live track: existing .lrc -> status ok + indexed, missing -> pending.
    a row skipped for lack of a lyric goes back to pending once the file exists.
    '''
    if system_state.is_initializing_lyrics:
        return
    system_state.init_lyric_state()
    progress = system_state.lyric_init_progress
    if progress is None:      # just created by init_lyric_state(), narrow the type
        system_state.is_initializing_lyrics = False
        return
    try:
        async with AsyncSessionLocal() as db:
            service = LyricIndexService(db, settings)
            created = await service.align_rows()
            await db.commit()
            logger.info(f'🎵Lyric init: {created} track(s) without lyric row were aligned.')

            rows = (await db.execute(select(Lyric.id, Lyric.path).order_by(Lyric.id))).all()
            progress['total'] = len(rows)

            for index, (lyric_id, lyric_path) in enumerate(rows, 1):
                if system_state.is_lyric_init_canceled:
                    logger.info('🎵Lyric init canceled by user.')
                    break
                result = await service.sync_file_state(lyric_id, lyric_path)
                progress['processed'] = index
                if result == 'ok':
                    progress['ok'] += 1
                else:
                    progress['pending'] += 1
                progress['current_file'] = lyric_path
                if index % BATCH_SIZE == 0:
                    await db.commit()
                    await asyncio.sleep(0)

            await db.commit()

        logger.info(f'🎵Lyric init finished: {progress}')
    except Exception as e:
        logger.error(f'❌Lyric init failed: {e}', exc_info=True)
    finally:
        system_state.is_initializing_lyrics = False


@router.post('/init', response_model=ResponseModel[None])
async def init_lyrics(background_tasks: BackgroundTasks, current_user: CurrentUser = Depends(require_admin)):
    '''align lyrics with tracks and index existing lyric files (manual, from the frontend)'''
    if system_state.is_initializing_lyrics:
        raise BusinessException(
            code=70801,
            msg='lyric init is already running.',
            status_code=status.HTTP_409_CONFLICT
        )
    background_tasks.add_task(run_lyric_init_task)
    logger.info(f'🎵{current_user.username} started the lyric table init.')
    return ResponseModel(code=200, msg='ok', data=None)


@router.post('/cancel', response_model=ResponseModel[None])
async def cancel_init(current_user: CurrentUser = Depends(require_admin)):
    '''cancel the running lyric init task'''
    if system_state.is_initializing_lyrics:
        system_state.cancel_lyric_init()
        logger.info(f'🎵{current_user.username} canceled the lyric table init.')
    return ResponseModel(code=200, msg='ok', data=None)


async def run_lyric_fetch_task(limit: int = 1000):
    '''
    feed every pending / failed lyric row to the fetcher thread.

    results are written back by the on_result callback, so the endpoint returns
    as soon as the queue is filled; the worker keeps going in the background.
    '''
    if system_state.is_fetching_lyrics:
        return
    system_state.is_fetching_lyrics = True
    try:
        loop = asyncio.get_running_loop()

        async def persist(result):
            try:
                async with AsyncSessionLocal() as db:
                    await LyricIndexService(db, settings).apply_fetch_result(result)
                    await db.commit()
            except Exception as e:
                logger.error(f'❌Persist lyric result failed: {result.path}: {e}')

        lyric_service.on_result = lambda res: asyncio.run_coroutine_threadsafe(persist(res), loop)

        async with AsyncSessionLocal() as db:
            tracks = await LyricIndexService(db, settings).fetch_candidates(limit)

        queued = sum(1 for track in tracks if lyric_service.submit(track))
        logger.info(f'🎵Incremental lyric fetch: {queued}/{len(tracks)} track(s) queued.')
    except Exception as e:
        logger.error(f'❌Incremental lyric fetch failed: {e}', exc_info=True)
    finally:
        system_state.is_fetching_lyrics = False


@router.post('/fetch', response_model=ResponseModel[None])
async def fetch_pending_lyrics(background_tasks: BackgroundTasks, limit: int = 1000,
                               current_user: CurrentUser = Depends(require_admin)):
    '''incremental fetch: only pending / failed rows are processed'''
    if system_state.is_fetching_lyrics:
        raise BusinessException(
            code=70803,
            msg='lyric fetch is already running.',
            status_code=status.HTTP_409_CONFLICT
        )
    background_tasks.add_task(run_lyric_fetch_task, limit)
    logger.info(f'🎵{current_user.username} started an incremental lyric fetch.')
    return ResponseModel(code=200, msg='ok', data=None)


@router.post('/import/fetch', response_model=ResponseModel[dict])
async def import_fetch_result(db: DbDep, file: UploadFile = File(...),
                              current_user: CurrentUser = Depends(require_admin)):
    '''import the fetch result csv exported from the external sqlite database'''
    content = await file.read()
    stats = await LyricImportService(db, settings).import_fetch_csv(content)
    logger.info(f'🎵{current_user.username} imported lyric fetch result: {stats}')
    return ResponseModel(code=200, msg='ok', data=stats)


@router.get('/export/best', response_class=StreamingResponse)
async def export_best_line(db: DbDep, limit: int | None = Query(None, ge=1),
                           current_user: CurrentUser = Depends(require_admin)):
    '''export every pending best line row, the external extractor fills the best field'''
    items = await LyricImportService(db, settings).export_best_json(limit)
    payload = json.dumps(items, ensure_ascii=False).encode('utf-8')
    filename = f'lyric_best_pending_{datetime.now():%Y%m%d%H%M%S}.json'
    logger.info(f'🎵{current_user.username} exported {len(items)} pending lyric best row(s).')
    return StreamingResponse(
        content=BytesIO(payload),
        media_type='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(len(payload)),
            'X-Exported-Count': str(len(items)),
            'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length, X-Exported-Count',
        },
    )


@router.post('/import/best', response_model=ResponseModel[dict])
async def import_best_line(db: DbDep, file: UploadFile = File(...),
                           current_user: CurrentUser = Depends(require_admin)):
    '''import the best line json, rows of the export round not covered become terminal skip'''
    content = await file.read()
    try:
        stats = await LyricImportService(db, settings).import_best_json(content)
    except ValueError as e:
        raise BusinessException(code=70802, msg=str(e), status_code=status.HTTP_400_BAD_REQUEST)
    logger.info(f'🎵{current_user.username} imported lyric best line: {stats}')
    return ResponseModel(code=200, msg='ok', data=stats)


@router.get('/status', response_model=ResponseModel[dict])
async def lyric_status(db: DbDep, _: CurrentUser = Depends(require_admin)):
    '''lyric init progress and lyric table statistics'''
    counts = await LyricIndexService(db, settings).status_counts()
    return ResponseModel(code=200, msg='ok', data={
        'is_initializing': system_state.is_initializing_lyrics,
        'progress': system_state.lyric_init_progress,
        **counts,
    })
