# -*- encoding: utf-8 -*-
'''
@File      :   upload.py
@Time      :   2025/10/25 11:32:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   upload, stagging and archive router
'''


from fastapi import APIRouter, UploadFile, Form, Query, Depends, Response, status
from app.services.file_service import FileService, ArchiveService
from app.services.fetchcoverart import get_cover_art, cover_cache
from app.core.deps import SettingsDep, ADMIN_DEPS
from app.core.config import settings
from app.core.exceptions import BusinessException
from app.utils.aidmatch import generate_fingerprint, match_fingerprint
from app.schemas.common import ResponseModel, CountResponse
from app.schemas.filething import (
    FileBase, SessionBase, SessionListResponse, FileInfoListResponse, UpdateVerionList, UpdateMetaTagsList,
    CreateArchive, ArchiveResponse, CreateFingerprint, Fingerprint, MatchAcoustResponse, DeleteStagingFiles,
    CheckTrackFileRequest, CheckTrackFileResponse
)
from app.services.file_service import FileCheckService
from typing import Annotated

router = APIRouter(dependencies=ADMIN_DEPS)

@router.post('/uploadfile', response_model=ResponseModel[FileBase])
async def upload_file(file: UploadFile, name: Annotated[str | None, Form()] = None, service: FileService = Depends(FileService)):
    if file.content_type not in ['audio/mpeg', 'audio/flac']:
        raise BusinessException(
            code=70315, 
            msg='only mp3 and flac files are allowed', 
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        )
    content = await file.read()
    if name:
        filename = name
    else:
        filename = file.filename
    _ = await service.save_temp_file(content, filename)
    await file.close()
    return ResponseModel(data=FileBase(filename=filename))

@router.post('/staging/session', response_model=ResponseModel[SessionBase])
async def create_session(service: FileService = Depends(FileService)):
    session_id = service.create_staging_session()
    return ResponseModel(data=SessionBase(session_id=session_id))

@router.get('/staging/sessions', response_model=ResponseModel[SessionListResponse])
async def list_staging_sessions(service: FileService = Depends(FileService)):
    '''list all staging sessions'''
    sessions = service.list_sessions()
    return ResponseModel(data=SessionListResponse.model_validate({'sessions': sessions}))

@router.get('/staging/sessions/{session_id}/files', response_model=ResponseModel[FileInfoListResponse])
async def get_session_files(session_id: str, service: FileService = Depends(FileService)):
    try:
        files = service.list_session_files(session_id)
        return ResponseModel(data=FileInfoListResponse(files))
    except FileNotFoundError:
        raise BusinessException(
            code=70302, 
            msg='session not found', 
            status_code=status.HTTP_404_NOT_FOUND, 
        )
    except Exception:
        raise BusinessException(
            code=70303, 
            msg='error when get session file info', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )

@router.post('/staging/sessions/{session_id}/files', response_model=ResponseModel[FileInfoListResponse])
async def add_file_to_session(
    session_id: str, 
    settings: SettingsDep,
    service: FileService = Depends(FileService), 
    temp_file_id: Annotated[
        str | None, 
        Query(description='Optional: specific temp file ID. If not provided, will move all files in temp to staging.')
    ] = None
):
    # 1. 将temp文件移入指定的staging会话
    moved = []
    session_dir = settings.STAGING_DIR / session_id
    if not session_dir.exists():
        raise BusinessException(
            code=70302, 
            msg='session not found', 
            status_code=status.HTTP_404_NOT_FOUND, 
        )
    
    try:
        if temp_file_id is None:
            # 批量移动所有temp文件
            moved = service.move_all_to_staging(session_id)
        else:
            # 移动单个temp文件
            moved.append(service.move_single_to_staging(session_id, temp_file_id))
    except FileNotFoundError:
        raise BusinessException(
            code=70304, 
            msg='file not found when moving', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )
    except Exception:
        raise BusinessException(
            code=70305, 
            msg='error when moving file', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )
    
    # 2. 获取所有文件的信息
    try:
        files = service.list_session_files(session_id, moved)
        return ResponseModel(data=FileInfoListResponse(files))
    except Exception:
        raise BusinessException(
            code=70303, 
            msg='error when get session file info', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )
    
@router.post('/staging/sessions/{session_id}/updateversion', response_model=ResponseModel[CountResponse])
async def update_version(session_id: str, input: UpdateVerionList, service: FileService = Depends(FileService)):
    try:
        for item in input.items:
            service.update_file_version(session_id, item.id, item.use_apev2)
        return ResponseModel(data=CountResponse(count=len(input.items)))
    except Exception:
        raise BusinessException(
            code=70307, 
            msg='error when update file meta version', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )

@router.post('/staging/sessions/{session_id}/updatemetatags', response_model=ResponseModel[CountResponse])
async def update_metatags(session_id: str, input: UpdateMetaTagsList, service: FileService = Depends(FileService)):
    try:
        batch_count = input.batch_count
        if batch_count <= 0:
            raise BusinessException(
                code=70308, 
                msg='invalid batch count', 
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if batch_count > settings.MAX_UPDATE_META_BATCH_COUNT:
            raise BusinessException(
                code=70309, 
                msg='batch count overload', 
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    except ValueError:
        raise BusinessException(
            code=70308, 
            msg='invalid batch count', 
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    
    try:
        for item in input.items:
            print(item.model_dump())
            data = {k: v for k, v in item.model_dump().items() if k != 'id'}
            service.update_file_metatags(session_id, item.id, data)
        return ResponseModel(data=CountResponse(count=len(input.items)))
    except Exception:
        raise BusinessException(
            code=70307, 
            msg='error when update file meta tags', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )

# @router.post('/staging/sessions/{session_id}/updatemetadatas', response_model=ResponseModel[CountResponse])
# async def update_metadatas(session_id: str, request: Request, settings: SettingsDep, service: FileService = Depends(FileService)):
#     form_data = await request.form()
#     try:
#         batch_count = int(form_data.get('batch_count', 0))
#         if batch_count <= 0:
#             raise HTTPException(status_code=400, detail='Invalid batch count')
#         if batch_count > settings.MAX_UPDATE_META_BATCH_COUNT:
#             raise HTTPException(status_code=400, detail='Batch count overload')
#     except ValueError:
#         raise HTTPException(status_code=400, detail='Invalid batch count')
    
#     success_count = 0
#     fail_count = 0
#     fail_details = []

#     for k, v in form_data.items():
#         meta_data = None
#         cover = None
#         cover_data = None
#         if k.startswith('meta_'):
#             try:
#                 meta_id = k.split('_', 1)[1]
#                 try:
#                     meta_data = json.loads(v)
#                 except json.JSONDecodeError:
#                     fail_details.append(f'Invalid JSON for meta_id: {meta_id}')
#                     fail_count += 1
#                     continue
#                 cover = form_data.get(f'cover_{meta_id}')
#                 if cover and not isinstance(cover, str):
#                     if cover.size > settings.MAX_META_COVER_SIZE:
#                         fail_details.append(f'Cover art size exceeds limit for meta_id: {meta_id}')
#                         fail_count += 1
#                         continue
#                     cover_data = await cover.read()
#                     meta_data['cover_art_data'] = cover_data
#                     await cover.close()
#                 service.update_file_metatags(session_id, meta_id, meta_data)
#                 success_count += 1
#             except Exception as e:
#                 fail_count += 1
#                 fail_details.append(f'Error when update metadata: {str(e)[:100]}')
#             finally:
#                 del meta_data, cover, cover_data
#                 gc.collect()
#     if success_count != batch_count:
#         raise BusinessException(code=1002, msg='partial success', detail='\n'.join(fail_details))
#     return ResponseModel(data=CountResponse(count=success_count))

@router.post('/staging/sessions/{session_id}/deletefiles', response_model=ResponseModel[CountResponse])
async def delete_staging_files(session_id: str, input: DeleteStagingFiles, service: FileService = Depends(FileService)):
    try:
        count = service.delete_staging_files(session_id, input.items)
        return ResponseModel(data=CountResponse(count=count))
    except FileNotFoundError:
        raise BusinessException(
            code=70302,
            msg='session not found',
            status_code=status.HTTP_404_NOT_FOUND,
        )
    except Exception:
        raise BusinessException(
            code=70317,
            msg='error when delete staging files',
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@router.post('/staging/sessions/{session_id}/archive', response_model=ResponseModel[ArchiveResponse])
async def archive_session_route(
    session_id: str,
    input: CreateArchive,
    lang: str | None = 'CN', 
    service: ArchiveService = Depends(ArchiveService),
):
    errors = await service.archive_session(session_id, input.items, lang, input.is_use_original_name, input.playlist)
    if errors:
        errors_str = '\n  '.join([f"{item['file']}: {item['error']}" for item in errors])
        error_files = [item['file'] for item in errors]
        raise BusinessException(
            code=70306, 
            msg=f'archive track file partial success: \n{errors_str}', 
            detail={'errors': errors_str} if settings.DEBUG else {'errors': error_files},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return ResponseModel(data=ArchiveResponse(archived=True))

@router.post('/staging/sessions/fingerprint', response_model=ResponseModel[Fingerprint])
async def fingerprint(fp_input: CreateFingerprint, settings: SettingsDep):
    file_path = settings.STAGING_DIR / fp_input.session_id / 'songs' / fp_input.filename
    try:
        duration, fp = generate_fingerprint(file_path)
    except RuntimeError as e:
        raise BusinessException(
            code=70311, 
            msg='error when generate fingerprint', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )
    return ResponseModel(data=Fingerprint(duration=duration, fingerprint=fp))

@router.post('/staging/sessions/match', response_model=ResponseModel[MatchAcoustResponse])
async def match(fingerprint: Fingerprint):
    try:
        acoust_info_list = match_fingerprint(fingerprint.duration, fingerprint.fingerprint)
    except RuntimeError as e:
        raise BusinessException(
            code=70312, 
            msg='error when match song metadata', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )
    return ResponseModel(data=MatchAcoustResponse(matched_list=acoust_info_list))

@router.get('/staging/coverart/{release_id}')
async def get_cover(release_id: str):
    try:
        cover_data = get_cover_art(release_id)
    except Exception as e:
        raise BusinessException(
            code=70313, 
            msg='error when fetch cover art', 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        )
    if cover_data is None:
        raise BusinessException(
            code=70314, 
            msg='cover art not found', 
            status_code=status.HTTP_404_NOT_FOUND, 
        )
    return Response(
        content=cover_data,
        media_type='image/jpeg',
        headers={
            'Cache-Control': f'max-age={settings.CACHE_EXPIRE}',
            'X-Cache-Status': 'HIT' if release_id in cover_cache else 'MISS'
        }
    )

# ======= check track files before upload to music library =======
@router.post('/checktrackfiles', response_model=ResponseModel[CheckTrackFileResponse])
async def check_track_files(input: CheckTrackFileRequest, service: FileCheckService = Depends(FileCheckService)):
    total, valid, parsed = service.parse_content(input.list_text)
    result = await service.check_file_exist(parsed)
    return ResponseModel(data=CheckTrackFileResponse(
        total=total, 
        valid=valid, 
        matched=result[0], 
        unmatched=result[1]
    ))
