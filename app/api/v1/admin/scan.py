# -*- encoding: utf-8 -*-
'''
@File      :   scan.py
@Time      :   2025/10/20 14:08:33
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router scan
'''


from fastapi import APIRouter, BackgroundTasks, Depends
from app.core.config import settings
from app.core.state import system_state
from app.core.deps import require_admin
from app.services.scanner import cancel_scan, scan_music_library
from app.background.watcher import start_watcher, stop_watcher
from app.models.user import User
from app.schemas.common import ResponseModel
from app.schemas.sysinfo import ScanInfo
from typing import Any

import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post('/start', response_model=ResponseModel[None])
async def trigger_scan(background_tasks: BackgroundTasks, current_user: User = Depends(require_admin)):
    background_tasks.add_task(scan_music_library, settings.MUSIC_LIBRARY_PATH)
    logger.info(f"{current_user.username} started the scanner in background.")
    return ResponseModel(code=200, msg='ok', data=None)

@router.post('/cancel', response_model=ResponseModel[None])
def cancel_scan_route(current_user: User = Depends(require_admin)):
    cancel_scan()
    logger.info(f"{current_user.username} canceled the scanner.")
    return ResponseModel(code=200, msg='ok', data=None)

@router.get('/progress', response_model=ResponseModel[ScanInfo])
async def get_scan_progress(_: User = Depends(require_admin)):
    return ResponseModel(code=200, msg='ok', data=ScanInfo(
        is_running=system_state.is_scanning, 
        progress=system_state.scan_progress
    ))

@router.post('/startwatcher', response_model=ResponseModel[None])
async def start_watcher(current_user: User = Depends(require_admin)):
    start_watcher()
    logger.info(f"👀{current_user.username} started the file watcher.")
    return ResponseModel(code=200, msg='ok', data=None)

@router.post('/stopwatcher', response_model=ResponseModel[None])
async def stop_watcher(current_user: User = Depends(require_admin)):
    stop_watcher()
    logger.info(f"👀{current_user.username} stopped the file watcher.")
    return ResponseModel(code=200, msg='ok', data=None)