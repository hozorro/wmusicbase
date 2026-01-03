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
from io import StringIO
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.core.deps import SettingsDep
from app.core.deps import ADMIN_DEPS
from app.core.exceptions import BusinessException
from app.schemas.common import ResponseModel, SuccessMsgModel
from app.schemas.filething import PlaylistJsonListResponse
from app.schemas.playback import ImportJsonUpload, PlaylistJsonUpload, JsonImportResponse
from app.schemas.user import UserListResponse
from app.services.playback_service import PlaylistService, PlayDataService
from app.services.user_service import UserService

router = APIRouter(dependencies=ADMIN_DEPS, tags=['backup'])

@router.get('/gettempplaylistjsons', response_model=ResponseModel[PlaylistJsonListResponse])
async def get_temp_playlist_jsons(settings: SettingsDep, service: PlaylistService = Depends(PlaylistService)):
    playlists = []
    for json_file in settings.PLAYLISTS_TMP_DIR.glob('*.json'):
        playlist = await service.parse_playlist_json_file(json_file)
        playlists.append(playlist)
    return ResponseModel(data=PlaylistJsonListResponse.model_validate(playlists))

@router.get('/getcurplaylists', response_model=ResponseModel[PlaylistJsonListResponse])
async def get_cur_playlists(service: PlaylistService = Depends(PlaylistService)):
    playlists = await service.get_user_playlists_info()
    return ResponseModel(data=PlaylistJsonListResponse.model_validate(playlists))

@router.get('/getallplaylists', response_model=ResponseModel[PlaylistJsonListResponse])
async def get_all_playlists(service: PlaylistService = Depends(PlaylistService)):
    playlists = await service.get_user_playlists_info(all_user=True)
    return ResponseModel(data=PlaylistJsonListResponse.model_validate(playlists))

@router.post('/createplaylistfromjson', response_model=ResponseModel[SuccessMsgModel])
async def create_playlist_from_json(filename: str, service: PlaylistService = Depends(PlaylistService)):
    result = await service.create_playlist_from_json(filename)
    return ResponseModel(data=SuccessMsgModel(info=result))
    
@router.post('/backupplaylist', response_model=ResponseModel[SuccessMsgModel])
async def backup_playlist(playlist_id: int, service: PlaylistService = Depends(PlaylistService)):
    try:
        await service.backup_user_playlist_to_json(playlist_id)
        return ResponseModel(data=SuccessMsgModel(info='backup successfully'))
    except Exception as e:
        raise BusinessException(code=10501, msg='backup error', detail=str(e))
    
@router.delete('/deleteplaylistjson', response_model=ResponseModel[SuccessMsgModel])
async def delete_playlist_json(filename: str, settings: SettingsDep):
    json_file = settings.PLAYLISTS_TMP_DIR / filename
    if not json_file.exists():
        raise BusinessException(code=10502, msg='json file not exists', detail=f'{filename}')
    json_file.unlink()
    return ResponseModel(data=SuccessMsgModel(info='successfully deleted'))

@router.get('/getuserlist', response_model=ResponseModel[UserListResponse])
async def get_user_list(service: UserService = Depends(UserService)):
    users = await service.get_user_list()
    return ResponseModel(data=UserListResponse(users))

@router.get('/exportuserplaylistdata', response_class=StreamingResponse)
async def export_user_playlist_data(user_id: int, service: PlayDataService = Depends(PlayDataService)):
    data = await service.get_user_playlist_data(user_id)
    json_string = json.dumps(data, ensure_ascii=False, sort_keys=False)

    buffer = StringIO()
    buffer.write(json_string)
    buffer.seek(0)

    filename = f'user_playlist_data_{data['user']}(id_{user_id}).json'
    return StreamingResponse(
        content=buffer,
        media_type='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(len(buffer.getvalue()))
        }
    )

@router.get('/exportuserhitdata', response_class=StreamingResponse)
async def export_user_hit_data(user_id: int, service: PlayDataService = Depends(PlayDataService)):
    data = await service.get_user_hits_data(user_id)
    json_string = json.dumps(data, ensure_ascii=False, sort_keys=False)

    buffer = StringIO()
    buffer.write(json_string)
    buffer.seek(0)

    filename = f'user_hit_data_{data['user']}(id_{user_id}).json'
    return StreamingResponse(
        content=buffer,
        media_type='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(len(buffer.getvalue()))
        }
    )

@router.get('/exportuserfavdata', response_class=StreamingResponse)
async def export_user_fav_data(user_id: int, service: PlayDataService = Depends(PlayDataService)):
    data = await service.get_user_favorites_data(user_id)
    json_string = json.dumps(data, ensure_ascii=False, sort_keys=False)

    buffer = StringIO()
    buffer.write(json_string)
    buffer.seek(0)

    filename = f'user_fav_data_{data['user']}(id_{user_id}).json'
    return StreamingResponse(
        content=buffer,
        media_type='application/json',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(len(buffer.getvalue()))
        }
    )

@router.post('/importplaylistdata', response_model=ResponseModel[JsonImportResponse])
async def import_playlist_data(
    item: PlaylistJsonUpload = Depends(),   # add "=Depends()" to receive attached variable data of UploadFile
    service: PlayDataService = Depends(PlayDataService)
):
    file = item.file
    is_update = item.is_update
    # 1. 校验文件
    data = await service.validate_upload_file(file, 'playlists')
    # 2. 导入数据
    result = await service.import_playlist_from_json(item.user_id, data, is_update)
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
    data = await service.validate_upload_file(file, 'favs')
    result = await service.import_fav_from_json(item.user_id, data)
    return ResponseModel(data=JsonImportResponse.model_validate(result))