# -*- encoding: utf-8 -*-
'''
@File      :   backup.py
@Time      :   2025/11/27 11:16:13
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   backup and restore
'''


import json
from io import StringIO, BytesIO
from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from app.core.deps import SettingsDep, ADMIN_DEPS
from app.core.exceptions import BusinessException
from app.schemas.common import ResponseModel, SuccessMsgModel
from app.schemas.filething import PlaylistJsonListResponse, PlaylistBackupResponse
from app.schemas.playback import ImportJsonUpload, PlaylistJsonUpload, JsonImportResponse
from app.schemas.user import UserDetail, UserResponse
from app.services.playback_service import PlaylistService, PlayDataService
from app.services.user_service import UserService

router = APIRouter(dependencies=ADMIN_DEPS)

@router.get('/gettmpplaylistjsons', response_model=ResponseModel[PlaylistBackupResponse])
async def get_temp_playlist_jsons(settings: SettingsDep, service: PlaylistService = Depends(PlaylistService)):
    playlists = []
    for json_file in settings.PLAYLISTS_TMP_DIR.glob('*.json'):
        playlist = await service.parse_playlist_json_file(json_file)
        playlists.append(playlist)
    return ResponseModel(data=PlaylistBackupResponse.model_validate(playlists))

@router.get('/getcurplaylists', response_model=ResponseModel[PlaylistBackupResponse])
async def get_cur_playlists(service: PlaylistService = Depends(PlaylistService)):
    playlists = await service.get_user_playlists_info()
    return ResponseModel(data=PlaylistBackupResponse.model_validate(playlists))

@router.get('/getallplaylists', response_model=ResponseModel[PlaylistBackupResponse])
async def get_all_playlists(service: PlaylistService = Depends(PlaylistService)):
    playlists = await service.get_user_playlists_info(all_user=True)
    return ResponseModel(data=PlaylistBackupResponse.model_validate(playlists))

@router.post('/createplaylistfromjson', response_model=ResponseModel[SuccessMsgModel])
async def create_playlist_from_json(filename: str, service: PlaylistService = Depends(PlaylistService)):
    result = await service.create_playlist_from_json(filename)
    return ResponseModel(data=SuccessMsgModel(info=result))
    
@router.get('/backupplaylist', response_class=StreamingResponse)
async def backup_playlist(playlist_id: int, service: PlaylistService = Depends(PlaylistService)):
    try:
        data = await service.get_playlist_data(playlist_id)
        json_string = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
        json_bytes = json_string.encode('utf-8')
        
        buffer = BytesIO(json_bytes)
        
        return StreamingResponse(
            content=buffer,
            media_type='application/json',
            headers={
                'Content-Disposition': f'attachment; filename="playlist_{playlist_id}.json"',
                'Content-Length': str(len(json_bytes)),
                'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length',
            }
        )
    except Exception as e:
        raise BusinessException(
            code=70501, 
            msg=f'playlist backup error: {str(e)}', 
            detail={'playlist_id': playlist_id}, 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
@router.delete('/deleteplaylistjson', response_model=ResponseModel[SuccessMsgModel])
async def delete_playlist_json(filename: str, settings: SettingsDep):
    json_file = settings.PLAYLISTS_TMP_DIR / filename
    if not json_file.exists():
        raise BusinessException(
            code=70504, 
            msg='playlist json file not exists', 
            detail={'filename': filename}, 
            status_code=status.HTTP_404_NOT_FOUND
        )
    json_file.unlink()
    return ResponseModel(data=SuccessMsgModel(info='successfully deleted'))

@router.get('/getuserlist', response_model=ResponseModel[list[UserDetail]])
async def get_user_list(service: UserService = Depends(UserService)):
    users = await service.get_user_list()
    return ResponseModel(data=[UserDetail.model_validate(u) for u in users])

@router.get('/exportuserplaylistdata', response_class=StreamingResponse)
async def export_user_playlist_data(user_id: int, service: PlaylistService = Depends(PlaylistService)):
    try:
        data = await service.get_user_playlist_data(user_id)
        json_string = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
        json_bytes = json_string.encode('utf-8')
        
        buffer = BytesIO(json_bytes)

        filename = f'user_{user_id}_playlists.json'
        return StreamingResponse(
            content=buffer,
            media_type='application/json',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(len(json_bytes)),
                'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length',
            }
        )
    except Exception as e:
        raise BusinessException(
            code=70503, 
            msg=f'user playlists backup error: {str(e)}', 
            detail={'user_id': user_id}, 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get('/exportuserhitdata', response_class=StreamingResponse)
async def export_user_hit_data(user_id: int, service: PlayDataService = Depends(PlayDataService)):
    try:
        data = await service.get_user_track_hits_data(user_id)
        json_string = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
        json_bytes = json_string.encode('utf-8')
        
        buffer = BytesIO(json_bytes)

        filename = f'user_{user_id}_hit.json'
        return StreamingResponse(
            content=buffer,
            media_type='application/json',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(len(json_bytes)),
                'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length',
            }
        )
    except Exception as e:
        raise BusinessException(
            code=70502, 
            msg=f'user hits data backup error: {str(e)}', 
            detail={'user_id': user_id}, 
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@router.get('/exportuserfavdata', response_class=StreamingResponse)
async def export_user_fav_data(user_id: int, service: PlayDataService = Depends(PlayDataService)):
    data = await service.get_user_track_favorites_data(user_id)
    json_string = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False)
    json_bytes = json_string.encode('utf-8')
    
    buffer = BytesIO(json_bytes)

    filename = f'user_{user_id}_fav_data.json'
    return StreamingResponse(
        content=buffer,
        media_type='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(len(json_bytes)),
            'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length',
        }
    )

@router.post('/importplaylistdata', response_model=ResponseModel[JsonImportResponse])
async def import_playlist_data(
    item: PlaylistJsonUpload = Depends(),   # add "=Depends()" to receive attached variable data of UploadFile
    service: PlayDataService = Depends(PlayDataService)
):
    file = item.file
    mode = item.mode
    # 1. 校验文件
    data = await service.validate_upload_file(file, 'playlists')
    # 2. 导入数据
    result = await service.import_playlist_from_json(item.user_id, data, mode)
    return ResponseModel(data=JsonImportResponse.model_validate(result))

@router.post('/importhitdata', response_model=ResponseModel[JsonImportResponse])
async def import_hit_data(
    item: ImportJsonUpload = Depends(),
    service: PlayDataService = Depends(PlayDataService)
):
    file = item.file
    data = await service.validate_upload_file(file, 'hits')
    result = await service.import_hit_from_json(item.user_id, data)
    return ResponseModel(data=JsonImportResponse.model_validate(result))

@router.post('/importfavdata', response_model=ResponseModel[JsonImportResponse])
async def import_fav_data(
    item: ImportJsonUpload = Depends(),
    service: PlayDataService = Depends(PlayDataService)
):
    file = item.file
    data = await service.validate_upload_file(file, 'favorites')
    result = await service.import_fav_from_json(item.user_id, data)
    return ResponseModel(data=JsonImportResponse.model_validate(result))