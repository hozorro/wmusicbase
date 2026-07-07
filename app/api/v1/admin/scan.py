# -*- encoding: utf-8 -*-
'''
@File      :   scan.py
@Time      :   2025/10/20 14:08:33
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   router scan
'''


import json, asyncio
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from app.core.state import system_state
from app.core.deps import require_admin, SettingsDep
from app.core.logger import logger
from app.core.exceptions import BusinessException
from app.services.scanner import Scanner
from app.services.folder_service import FolderService
from app.background.watcher_manager import watcher
from app.schemas.user import CurrentUser
from app.schemas.common import ResponseModel
from app.schemas.filething import ScanOptions
from app.schemas.sysinfo import ScanFolder

router = APIRouter()

async def run_scan_task(root_path: str, is_incremental: bool = False):
    if system_state.is_scanning:
        return
    scanner = Scanner(root_path, is_incremental)
    await scanner.run()

def cancel_scan_task():
    if system_state.is_scanning_canceled:
        return
    system_state.is_scanning_canceled = True

async def progress_generator(request: Request):
    '''
    generate progress stream for sse, consumer task.
    if client disconnect, stop sending progress.
    if set more than 1 worker in gunicorn, system_state can not be shared,
    scanning info should be shared(get/set) by redis.
    '''
    while True:
        if await request.is_disconnected():
            print("Client disconnected, stop sending scan progress.")
            break
        yield f'data: {json.dumps({
            "is_scanning": system_state.is_scanning,
            "scan_progress": system_state.scan_progress
        })}\n\n'

        await asyncio.sleep(0.5)

@router.get('/scanfolderinfo', response_model=ResponseModel[ScanFolder|None])
async def get_scan_folder_info(service: FolderService =  Depends(FolderService), _: CurrentUser = Depends(require_admin)):
    scan_folder_info = await service.get_scan_folder()
    if scan_folder_info:
        return ResponseModel(code=200, msg='ok', data=scan_folder_info)
    else:
        return ResponseModel(code=200, msg='ok', data=None)
@router.post('/start', response_model=ResponseModel[None])
async def trigger_scan(scan_options: ScanOptions,background_tasks: BackgroundTasks, settings: SettingsDep, current_user: CurrentUser = Depends(require_admin)):
    if system_state.is_scanning:
        return ResponseModel(code=200, msg='ok', data=None)
    background_tasks.add_task(run_scan_task, settings.MUSIC_LIBRARY_PATH, scan_options.is_incremental)
    logger.info(f"{current_user.username} started the scanner in background.")
    return ResponseModel(code=200, msg='ok', data=None)

@router.post('/cancel', response_model=ResponseModel[None])
def cancel_scan(current_user: CurrentUser = Depends(require_admin)):
    if system_state.is_scanning:
        cancel_scan_task()
    logger.info(f"{current_user.username} canceled the scanner.")
    return ResponseModel(code=200, msg='ok', data=None)
@router.get('/progress', response_class=StreamingResponse)
def scan_progress(request: Request, _: CurrentUser = Depends(require_admin)):
    return StreamingResponse(progress_generator(request), media_type='text/event-stream')

# ============ Watcher control (Development only) ============
# In production, watcher runs as an independent process managed by supervisor.
# These endpoints use watcher_manager.py for development/debugging without supervisor.
@router.post('/startwatcher', response_model=ResponseModel[None])
async def start_watcher(current_user: CurrentUser = Depends(require_admin)):
    '''Start the file watcher (development mode only, production uses supervisor)'''
    success, msg = watcher.start()
    if success:
        logger.info(f"👀{current_user.username} started the file watcher.")
        return ResponseModel(code=200, msg=msg, data=None)
    raise BusinessException(code=10500, msg=msg, detail='Failed to start watcher.')

@router.post('/stopwatcher', response_model=ResponseModel[None])
async def stop_watcher(current_user: CurrentUser = Depends(require_admin)):
    '''Stop the file watcher (development mode only, production uses supervisor)'''
    success, msg = watcher.stop()
    if success:
        logger.info(f"👀{current_user.username} stopped the file watcher.")
        return ResponseModel(code=200, msg=msg, data=None)
    raise BusinessException(code=10500, msg=msg, detail='Failed to stop watcher.')