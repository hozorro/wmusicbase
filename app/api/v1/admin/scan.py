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
from app.core.state import system_state
from app.core.deps import require_admin, SettingsDep, DbDep
from app.core.logger import logger
from app.services.scanner import cancel_scan, scan_music_library, get_scan_folder
from app.background.watcher import start_watcher, stop_watcher
from app.schemas.user import CurrentUser
from app.schemas.common import ResponseModel
from app.schemas.sysinfo import ScanFolder

router = APIRouter()

@router.get('/scanfolderinfo', response_model=ResponseModel[ScanFolder|None])
async def get_scan_folder_info(db: DbDep, _: CurrentUser = Depends(require_admin)):
    scan_folder_info = await get_scan_folder(db)
    if scan_folder_info:
        return ResponseModel(code=200, msg='ok', data=scan_folder_info)
    else:
        return ResponseModel(code=200, msg='ok', data=None)
@router.post('/start', response_model=ResponseModel[None])
async def trigger_scan(background_tasks: BackgroundTasks, settings: SettingsDep, current_user: CurrentUser = Depends(require_admin)):
    background_tasks.add_task(scan_music_library, settings.MUSIC_LIBRARY_PATH)
    logger.info(f"{current_user.username} started the scanner in background.")
    return ResponseModel(code=200, msg='ok', data=None)

@router.post('/cancel', response_model=ResponseModel[None])
def cancel_scan_route(current_user: CurrentUser = Depends(require_admin)):
    cancel_scan()
    logger.info(f"{current_user.username} canceled the scanner.")
    return ResponseModel(code=200, msg='ok', data=None)

@router.post('/startwatcher', response_model=ResponseModel[None])
async def start_watcher(current_user: CurrentUser = Depends(require_admin)):
    start_watcher()
    logger.info(f"👀{current_user.username} started the file watcher.")
    return ResponseModel(code=200, msg='ok', data=None)

@router.post('/stopwatcher', response_model=ResponseModel[None])
async def stop_watcher(current_user: CurrentUser = Depends(require_admin)):
    stop_watcher()
    logger.info(f"👀{current_user.username} stopped the file watcher.")
    return ResponseModel(code=200, msg='ok', data=None)