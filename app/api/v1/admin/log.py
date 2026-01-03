# -*- encoding: utf-8 -*-
'''
@File      :   log.py
@Time      :   2025/12/03 21:51:55
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   log route
'''


from io import StringIO
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from app.core.deps import ADMIN_DEPS
from app.services.log_service import LogService
from app.schemas.common import ResponseModel
from app.schemas.sysinfo import LogPageResponse, LogProperty

router = APIRouter(dependencies=ADMIN_DEPS)

@router.get('/types', response_model=ResponseModel[LogProperty])
async def get_log_types():
    data = {
        'log_types': [
            {'label': 'NORMAL', 'value': 'app'},
            {'label': 'ERROR', 'value': 'error'}
        ],
        'log_levels': [
            {'label': 'DEBUG', 'value': 'debug'},
            {'label': 'INFO', 'value': 'info'},
            {'label': 'WARNING', 'value': 'warning'},
            {'label': 'ERROR', 'value': 'error'},
            {'label': 'CRITICAL', 'value': 'critical'},
        ]
    }
    return ResponseModel(data=LogProperty.model_validate(data))

@router.get('', response_model=ResponseModel[LogPageResponse])
async def get_logs(
    log_type: str = Query('app', description='log type', enum=['app', 'error']),
    level: str | None = Query(None, description='log level', enum=['debug', 'info', 'warning', 'error', 'critical']),
    keyword: str | None = Query(None, description='log keyword(match msg and location)'),
    start_time: str | None = Query(None, description='log start time(ISO 8601 string)'),
    end_time: str | None = Query(None, description='log end time(ISO 8601 string)'),
    page: int = Query(1, description='page number', ge=1),
    page_size: int = Query(50, description='page size', ge=10, le=100),
    service: LogService = Depends(LogService),
):
    logs, total = service.read_logs(
        log_type=log_type,
        level=level,
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
        page=page,
        page_size=page_size,
    )
    return ResponseModel(
        data=LogPageResponse(
            logs=logs, 
            pagination={
                'total': total, 
                'page': page, 
                'page_size': page_size,
                'total_page': (total + page_size - 1) // page_size
            }
        ),
    )

@router.get('/export', response_class=StreamingResponse)
async def export_logs(
    log_type: str = Query('app', description='log type', enum=['app', 'error']),
    level: str | None = Query(None, description='log level', enum=['debug', 'info', 'warning', 'error', 'critical']),
    keyword: str | None = Query(None, description='log keyword(match msg and location)'),
    start_time: str | None = Query(None, description='log start time(ISO 8601 string)'),
    end_time: str | None = Query(None, description='log end time(ISO 8601 string)'),
    service: LogService = Depends(LogService),
):
    log_content = service.export_logs(
        log_type=log_type,
        level=level,
        keyword=keyword,
        start_time=start_time,
        end_time=end_time,
    )
    buffer = StringIO(log_content)
    buffer.seek(0)
    filename = f'log_{log_type}_{level}.log'

    return StreamingResponse(
        content=buffer,
        media_type='text/plain',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(len(buffer.getvalue()))
        }
    )