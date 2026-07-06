# -*- encoding: utf-8 -*-
'''
@File      :   artwork.py
@Time      :   2026/06/23 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   Artwork generation admin API
'''


import json, asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.state import system_state
from app.core.deps import require_admin
from app.core.db import AsyncSessionLocal
from app.core.logger import logger
from app.core.config import settings
from app.schemas.common import ResponseModel
from app.schemas.user import CurrentUser
from app.services.artwork_service import ArtworkService
from app.services.artwork_generator import ArtworkGenerator

router = APIRouter()


class ArtworkGenRequest(BaseModel):
    '''Request body for starting artwork generation'''
    art_types: list[str] | None = None  # None = all types, or ['artist', 'album', 'track', 'playlist']


async def run_artwork_gen_task(art_types: list[str] | None = None):
    '''Background task to run artwork generation'''
    if system_state.is_generating_artworks:
        return
    async with AsyncSessionLocal() as db:
        service = ArtworkService(db, settings)
        generator = ArtworkGenerator(service, art_types)
        await generator.run()


async def artwork_progress_generator(request: Request):
    '''
    SSE progress stream for artwork generation.
    Sends progress updates every 0.5 seconds.
    '''
    while True:
        if await request.is_disconnected():
            logger.info('Client disconnected, stop sending artwork progress.')
            break
        yield f'data: {json.dumps({
            "is_generating": system_state.is_generating_artworks,
            "artwork_progress": system_state.artwork_progress
        })}\n\n'
        await asyncio.sleep(0.5)


@router.post('/start', response_model=ResponseModel[None])
async def start_artwork_generation(
    data: ArtworkGenRequest | None = None,
    background_tasks: BackgroundTasks = None,
    current_user: CurrentUser = Depends(require_admin)
):
    '''
    Start artwork generation in background.
    art_types: None = generate all types, or specify list like ['artist', 'album']
    '''
    if system_state.is_generating_artworks:
        return ResponseModel(code=200, msg='ok', data=None)
    
    art_types = data.art_types if data else None
    background_tasks.add_task(run_artwork_gen_task, art_types)
    logger.info(f'{current_user.username} started artwork generation (types: {art_types or "all"})')
    return ResponseModel(code=200, msg='ok', data=None)


@router.post('/cancel', response_model=ResponseModel[None])
def cancel_artwork_generation(current_user: CurrentUser = Depends(require_admin)):
    '''Cancel ongoing artwork generation'''
    if system_state.is_generating_artworks:
        system_state.cancel_artwork_gen()
    logger.info(f'{current_user.username} canceled artwork generation.')
    return ResponseModel(code=200, msg='ok', data=None)


@router.get('/progress', response_class=StreamingResponse)
def artwork_generation_progress(request: Request, _: CurrentUser = Depends(require_admin)):
    '''
    SSE endpoint for artwork generation progress.
    Returns a stream of progress updates.
    '''
    return StreamingResponse(artwork_progress_generator(request), media_type='text/event-stream')
