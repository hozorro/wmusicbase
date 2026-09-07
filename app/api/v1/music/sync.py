# -*- encoding: utf-8 -*-
'''
@File      :   sync.py
@Time      :   2026/08/06 10:00:00
@Author    :   enauvy
@Version   :   2.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   route: sync musicbase data to client (indexeddb),
               paginated pull with incremental sync mode
'''


from datetime import datetime
from typing import get_args
from fastapi import APIRouter, Depends, status, Query
from app.services.sync_service import SyncService
from app.schemas.common import ResponseModel
from app.schemas.sync import StoreName, SyncPullResponse, SyncSummary
from app.core.exceptions import BusinessException

router = APIRouter()


@router.get('/summary', response_model=ResponseModel[SyncSummary])
async def get_sync_summary(
    since: datetime | None = Query(
        None, description='Last sync time (ISO 8601). Omit for full sync.'),
    service: SyncService = Depends(SyncService)
):
    '''
    Get sync summary.
    - counts: live record counts of six stores (tracks/albums/artists/genres/folders/playlists);
      for incremental sync (since given), counts of changed live records
    - deleted: soft-deleted ids per store, only carried for incremental sync
    - serverTime: server time snapshot (ISO 8601), as the `since` of next sync
    '''
    summary = await service.get_summary(since)
    return ResponseModel(data=SyncSummary(**summary))


@router.get('/pull', response_model=ResponseModel[SyncPullResponse])
async def pull_sync_data(
    store: StoreName = Query(..., description='Store name to pull'),
    since: datetime | None = Query(
        None, description='Last sync time (ISO 8601). Omit for full pull.'),
    after_id: int = Query(
        0, ge=0, description='Last synced id, records are ordered by id ascending'),
    size: int = Query(200, ge=1, le=1000, description='Page size'),
    service: SyncService = Depends(SyncService)
):
    '''
    Pull a page of records of the given store, ordered by id ascending.
    Returns items and next_after_id (null when the store pull is finished).
    '''
    if store not in get_args(StoreName):
        raise BusinessException(
            code=30601, 
            msg='invalid store name', 
            status_code=status.HTTP_400_BAD_REQUEST
        )
    result = await service.pull(store, since=since, after_id=after_id, size=size)
    return ResponseModel(data=SyncPullResponse(**result))
