# 错误响应机制与错误码清单

> 快照日期：2026-11-05。以 `app/` 下代码为准，改代码后需重新生成本文件。
>
> 业务异常 `raise BusinessException(...)` 共 **132 处**，
> 按 code + HTTP 状态 + msg + detail 去重后 **116 条**，
> 唯一业务码 **116 个**；另有 **5 条**系统级错误响应。

---

## 一、错误响应机制

### 1. 统一响应包络

不论错误来自业务代码、参数校验、框架路由还是中间件，响应体结构一致：

```json
{
  "code": 70801,
  "msg": "lyric init is already running.",
  "detail": null,
  "traceId": "9f2c1e7b8a4d4c53b6f0e1d2a3c4b5e6"
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `code` | int | 业务错误码，前端按码映射文案 |
| `msg` | str | 后端诊断信息，**不保证面向用户**，不建议直接展示 |
| `detail` | object \| null | 结构化上下文；校验失败时为 `{"fields": {字段: [{type, msg}]}}` |
| `traceId` | str \| null | 与响应头 `X-Request-Id` 一致，用于对照后端日志 |

### 2. 异常到响应的映射

处理器在 `app/main.py` 遍历 `EXCEPTION_HANDLERS` 注册：

| 异常 / 来源 | 处理器 | HTTP 状态 | 业务码 |
|---|---|---|---|
| `BusinessException` | `business_exception_handler` | 实例自带，默认 400 | 实例自带 |
| `RequestValidationError` | `validation_exception_handler` | 422 | `10422` |
| `StarletteHTTPException`（含 `fastapi.HTTPException`） | `http_exception_handler` | `exc.status_code` | `10xxx`，见下表 |
| `Exception` | `unhandled_exception_handler` | 500 | `10500` |
| `ScanMiddleware` | 中间件直接返回 | 423 | `10423` |

`http_exception_handler` 注册在 `StarletteHTTPException` 上，因此框架抛出的 404 / 405 与
业务代码抛出的 `fastapi.HTTPException` 走同一条路径，响应结构与其余错误完全一致。

### 3. HTTP 状态 → 业务码映射

映射表由 `app/core/exceptions.py` 的 `HTTP_STATUS_CODES` 决定，未列出的状态回退 `10500`：

| HTTP | code |
|---|---|
| 400 | `10400` |
| 401 | `10401` |
| 403 | `10403` |
| 404 | `10404` |
| 405 | `10405` |
| 409 | `10409` |
| 413 | `10413` |
| 415 | `10415` |
| 416 | `10416` |
| 422 | `10422` |
| 423 | `10423` |
| 429 | `10429` |
| 500 | `10500` |
| 502 | `10502` |
| 503 | `10503` |
| 504 | `10504` |
| 其它 | `10500` |

### 4. traceId 的来源

`TraceIdMiddleware`（`app/core/middleware.py:49`）优先取请求头 `X-Request-Id`，没有则生成 uuid4 hex，
写入 `request.state.trace_id` 并回填响应头。它是最外层中间件，因此 `ScanMiddleware` 的 423 响应
同样能读到并带出 `traceId`。

### 5. 错误码分段约定

| 段位 | 范围 | 用途 |
|---|---|---|
| `1xxxx` | 10001 ~ 19999 | 通用 / 框架 |
| `2xxxx` | 20001 ~ 29999 | 认证与鉴权 |
| `3xxxx` | 30001 ~ 39999 | 音乐主体（曲目 / 歌单 / 流媒体 / 网易云 / 同步） |
| `6xxxx` | 60001 ~ 69999 | 封面图与图片处理 |
| `7xxxx` | 70001 ~ 79999 | 管理端（编辑 / 上传 / 扫描 / 备份 / 歌词） |

新码在所属段位内递增，不复用、不跨段。

### 6. HTTP 状态码使用面

| 状态码 | 含义 |
|---|---|
| 400 | 参数非法 / 业务拒绝 |
| 401 | 未认证 / 凭证失效 |
| 403 | 已认证但无权限 |
| 404 | 资源不存在 |
| 405 | 请求方法不允许 |
| 409 | 状态冲突 |
| 413 | 请求体过大 |
| 415 | 媒体类型不支持 |
| 416 | Range 不合法 |
| 422 | 语义校验失败 |
| 423 | 资源锁定（扫描中） |
| 500 | 服务端错误 |
| 502 | 上游接口异常 |
| 503 | 服务不可用 |

---

## 二、系统级错误响应

不走 `BusinessException` 的响应，共 5 条。

| 来源 | code | HTTP | msg | detail | 触发条件 | 位置 |
|---|---|---|---|---|---|---|
| `exception_handler` | `exc.code` | exc.status_code（默认 400） | exc.msg | exc.detail | BusinessException 统一出口 | core/exceptions.py:70 |
| `exception_handler` | `10422` | 422 | Validation error | {'fields': {field: [{type, msg}]}} | 请求参数 / 请求体校验失败，按字段聚合 | core/exceptions.py:81 |
| `exception_handler` | `http_code_of(status)` | exc.status_code | exc.detail（字符串）否则 HTTP error | 非字符串 detail，否则 None | StarletteHTTPException 及其子类，覆盖 404 / 405 / 401 等 | core/exceptions.py:100 |
| `exception_handler` | `10500` | 500 | Internal Server Error | None | 未捕获异常兜底，同时 logger.exception 记录堆栈 | core/exceptions.py:122 |
| `middleware` | `10423` | 423 | System is busy scanning music library, Please wait... | None | ScanMiddleware：扫描期间除白名单外的所有请求 | core/middleware.py:42 |

---

## 三、业务错误码清单

> 同一组 code + 状态 + msg 的多次抛出合并为一行，`位置` 列出全部抛出点（路径省略 `app/` 前缀）。

### 1xxxx —— 通用 / 框架

范围 10001 ~ 19999，共 1 条。

| code | HTTP | msg | detail | 位置 |
|---|---|---|---|---|
| `10001` | 400 | `invalid client type, please set x-client-type header` | - | core/deps.py:43 |

### 2xxxx —— 认证与鉴权

范围 20001 ~ 29999，共 9 条。

| code | HTTP | msg | detail | 位置 |
|---|---|---|---|---|
| `20001` | 401 | `invalid credentials when login` | - | api/v1/auth.py:35 |
| `20002` | 401 | `invalid credentials when refresh token` | - | api/v1/auth.py:109 |
| `20003` | 403 | `registration closed after first user` | - | api/v1/auth.py:62 |
| `20004` | 401 | `invalid credentials when get current user token` | - | core/deps.py:80 |
| `20005` | 401 | `invalid credentials when get current user` | - | core/deps.py:108 |
| `20006` | 403 | `invalid credentials when check user as streaming` | - | services/file_service.py:299 |
| `20007` | 403 | `token type mismatch with endpoint` | - | core/deps.py:89、core/deps.py:97 |
| `20008` | 401 | `failed to verify token` | - | core/deps.py:119 |
| `20009` | 403 | `admin required` | - | core/deps.py:128 |

### 3xxxx —— 音乐主体（曲目 / 歌单 / 流媒体 / 网易云 / 同步）

范围 30001 ~ 39999，共 30 条。

| code | HTTP | msg | detail | 位置 |
|---|---|---|---|---|
| `30104` | 404 | `f'artist {artist_id} not found'` | - | services/artwork_service.py:565 |
| `30204` | 404 | `f'album not exists: {album_id}'` | `{'album_id': album_id}` | api/v1/music/album.py:27、services/artwork_service.py:707 |
| `30301` | 403 | `token expired when streaming track` | - | api/v1/stream.py:30 |
| `30302` | 403 | `invalid token when streaming track` | - | api/v1/stream.py:36 |
| `30303` | 403 | `token mismatch when streaming track` | - | api/v1/stream.py:47 |
| `30304` | 404 | `track file not found` | - | api/v1/stream.py:59、api/v1/stream.py:101 |
| `30305` | 404 | `track not found` | - | api/v1/music/track.py:31 |
| `30307` | 416 | `invalid range header` | - | utils/streaming.py:40 |
| `30308` | 404 | `f'track not exists: {track_id}'` | `{'track_id': track_id}` | services/track_service.py:41 |
| `30501` | 409 | `f'fail to create playlist with integrity error: {playlist.title}'` | - | services/playback_service.py:119 |
| `30502` | 500 | `f'fail to create playlist with unknown error: {playlist.title}'` | - | services/playback_service.py:127 |
| `30503` | 404 | `f'playlist not found when delete: {playlist_id}'` | - | services/playback_service.py:373 |
| `30504` | 404 | `playlist not found` | - | services/artwork_service.py:742 |
| `30505` | 404 | `f'track not found in playlist when move: {track_id}'` | - | services/playback_service.py:455 |
| `30506` | 400 | `f'invalid position when move track in playlist: {track_id}-{new_position}'` | - | services/playback_service.py:461 |
| `30507` | 500 | `error when create playlist` | - | api/v1/music/playback.py:64 |
| `30508` | 500 | `error when update playlist` | - | api/v1/music/playback.py:93 |
| `30509` | 409 | `track already exists in playlist` | - | api/v1/music/playback.py:126 |
| `30510` | 500 | `update successful but error when save playlist image` | - | api/v1/music/playback.py:109 |
| `30515` | 415 | `only jpg and png files are allowed for playlist images` | - | api/v1/music/playback.py:73、api/v1/music/playback.py:102 |
| `30520` | 400 | `either playlist_id or share_text must be provided` | - | api/v1/music/netease.py:57 |
| `30521` | 502 | `f'netease api request failed: {e.response.status_code}'` | - | services/netease_service.py:152 |
| `30522` | 502 | `netease api request failed: network error` | - | services/netease_service.py:159 |
| `30523` | 502 | `netease api request failed: unknown error` | - | services/netease_service.py:166 |
| `30524` | 404 | `playlist not found on netease` | - | services/netease_service.py:175、services/netease_service.py:183 |
| `30525` | 502 | `netease api request failed: song data processing error` | - | services/netease_service.py:215 |
| `30526` | 400 | `failed to extract playlist id from share text` | - | api/v1/music/netease.py:50 |
| `30527` | 500 | `f'error when create playlist: {str(e)}'` | - | api/v1/music/netease.py:109 |
| `30528` | 502 | `f'netease song info request failed: {last_desc}'` | - | services/netease_service.py:667 |
| `30601` | 400 | `invalid store name` | - | api/v1/music/sync.py:56 |

### 6xxxx —— 封面图与图片处理

范围 60001 ~ 69999，共 35 条。

| code | HTTP | msg | detail | 位置 |
|---|---|---|---|---|
| `60104` | 404 | `artist artwork not found` | - | api/v1/artwork.py:34 |
| `60105` | 404 | `candidate artist artwork not found` | - | api/v1/artwork.py:152 |
| `60106` | 500 | `f'failed to save artist art'` | - | api/v1/admin/edit.py:87 |
| `60107` | 400 | `art_type must be face or portrait` | - | api/v1/admin/edit.py:178、api/v1/admin/edit.py:234、api/v1/admin/edit.py:257、api/v1/admin/edit.py:292、services/artwork_service.py:974 |
| `60108` | 404 | `candidate artist artwork not found` | - | api/v1/admin/edit.py:186 |
| `60109` | 500 | `failed to upload artist art candidate` | - | api/v1/admin/edit.py:242 |
| `60110` | 500 | `failed to set artist art from candidate` | - | api/v1/admin/edit.py:265、services/artwork_service.py:1029 |
| `60113` | 413 | `file size exceeds 5MB limit` | `{'file_limit': '5MB'}` | api/v1/admin/edit.py:227 |
| `60115` | 415 | `only jpg and png files are allowed` | - | api/v1/admin/edit.py:78 |
| `60116` | 415 | `only jpg and png files are allowed` | - | api/v1/admin/edit.py:219 |
| `60117` | 500 | `failed to create artist directory` | - | api/v1/admin/edit.py:201 |
| `60120` | 502 | `f'third-party search api request failed: {status_code}'` | - | services/artwork_service.py:846 |
| `60121` | 502 | `third-party search api request failed: network error` | - | services/artwork_service.py:853 |
| `60122` | 502 | `third-party search api request failed: unknown error` | - | services/artwork_service.py:860 |
| `60123` | 404 | `temp artwork not found or expired` | - | api/v1/artwork.py:122 |
| `60124` | 400 | `invalid temp_id` | - | services/artwork_service.py:982 |
| `60125` | 404 | `temp artwork not found or expired` | - | services/artwork_service.py:991 |
| `60126` | 404 | `temp artwork expired` | - | services/artwork_service.py:1002 |
| `60127` | 502 | `third-party search api not configured` | - | services/artwork_service.py:812 |
| `60128` | 500 | `failed to download artist images` | - | services/artwork_service.py:895 |
| `60129` | 404 | `f'artist not found: {artist_name}'` | - | services/artwork_service.py:869 |
| `60130` | 500 | `f'failed to save artist art: {e}'` | - | services/artwork_service.py:1016 |
| `60204` | 404 | `album artwork not found` | - | api/v1/artwork.py:56 |
| `60205` | 500 | `cover art fetch error` | - | api/v1/artwork.py:78 |
| `60206` | 404 | `cover art not found` | - | api/v1/artwork.py:84 |
| `60207` | 500 | `f'failed to save album art'` | - | api/v1/admin/edit.py:106 |
| `60215` | 415 | `only jpg and png files are allowed` | - | api/v1/admin/edit.py:97 |
| `60304` | 404 | `track artwork not found` | - | api/v1/artwork.py:45 |
| `60305` | 404 | `tmp track artwork not found` | - | api/v1/artwork.py:108 |
| `60306` | 500 | `f'failed to update track cover: {str(e)[:100]}'` | - | api/v1/admin/edit.py:131 |
| `60315` | 415 | `only jpg and png files are allowed` | - | api/v1/admin/edit.py:121 |
| `60404` | 404 | `default artwork not found` | - | api/v1/artwork.py:137 |
| `60405` | 500 | `failed to set default artwork` | - | api/v1/artwork.py:174 |
| `60415` | 415 | `only jpg and png files are allowed` | - | api/v1/artwork.py:166 |
| `60504` | 404 | `playlist artwork not found` | - | api/v1/artwork.py:67 |

### 7xxxx —— 管理端（编辑 / 上传 / 扫描 / 备份 / 歌词）

范围 70001 ~ 79999，共 41 条。

| code | HTTP | msg | detail | 位置 |
|---|---|---|---|---|
| `70104` | 404 | `f'artist not exists: {artist_id}'` | `{'artist_id': artist_id}` | api/v1/admin/edit.py:55 |
| `70204` | 404 | `f'album not exists: {album_id}'` | `{'album_id': album_id}` | api/v1/admin/edit.py:67 |
| `70301` | 500 | `failed to move {temp_file} to stageing {dest}` | `{'temp_file': temp_file}` | services/file_service.py:81 |
| `70302` | 404 | `session not found` | - | api/v1/admin/upload.py:71、api/v1/admin/upload.py:97、api/v1/admin/upload.py:239 |
| `70303` | 500 | `error when get session file info` | - | api/v1/admin/upload.py:77、api/v1/admin/upload.py:128 |
| `70304` | 500 | `file not found when moving` | - | api/v1/admin/upload.py:111 |
| `70305` | 500 | `error when moving file` | - | api/v1/admin/upload.py:117 |
| `70306` | 500 | `f'archive track file partial success: \n{errors_str}'` | `{'errors': errors_str} if settings.DEBUG else {'errors': error_files}` | api/v1/admin/upload.py:262 |
| `70307` | 500 | `error when update file meta version` | - | api/v1/admin/upload.py:141 |
| `70308` | 400 | `invalid batch count` | - | api/v1/admin/upload.py:152、api/v1/admin/upload.py:164 |
| `70309` | 400 | `batch count overload` | - | api/v1/admin/upload.py:158 |
| `70310` | 400 | `filename is required when uploading file` | - | api/v1/admin/upload.py:45 |
| `70311` | 500 | `error when generate fingerprint` | - | api/v1/admin/upload.py:276 |
| `70312` | 500 | `error when match song metadata` | - | api/v1/admin/upload.py:288 |
| `70313` | 500 | `error when fetch cover art` | - | api/v1/admin/upload.py:300 |
| `70314` | 404 | `cover art not found` | - | api/v1/admin/upload.py:306 |
| `70315` | 415 | `only mp3 and flac files are allowed` | - | api/v1/admin/upload.py:33 |
| `70316` | 500 | `f'update track metadata partial success: \n{errors_str}'` | `{'errors': errors_paths}` | api/v1/admin/edit.py:144 |
| `70317` | 500 | `error when delete staging files` | - | api/v1/admin/upload.py:245 |
| `70318` | 500 | `f'user hits data backup error: {str(e)}'` | `{'user_id': user_id}` | api/v1/admin/backup.py:152 |
| `70319` | 500 | `error when update file meta tags` | - | api/v1/admin/upload.py:177 |
| `70501` | 500 | `f'playlist backup error: {str(e)}'` | `{'playlist_id': playlist_id}` | api/v1/admin/backup.py:80 |
| `70502` | 422 | `import playlist from json error` | - | services/playback_service.py:661 |
| `70503` | 500 | `f'user playlists backup error: {str(e)}'` | `{'user_id': user_id}` | api/v1/admin/backup.py:125 |
| `70504` | 404 | `playlist json file not exists` | `{'filename': filename}` | api/v1/admin/backup.py:91 |
| `70505` | 404 | `f'user not exists: {user_id}'` | `{'user_id': user_id}` | services/playback_service.py:191、services/playback_service.py:615、services/playback_service.py:636 |
| `70506` | 422 | `f'playlist json file has no valid title: {filename}'` | `{'filename': filename}` | services/playback_service.py:244 |
| `70507` | 404 | `f'playlist not exists: {playlist_id}'` | `{'playlist_id': playlist_id}` | api/v1/admin/backup.py:56 |
| `70601` | 415 | `upload playdata backup file type error` | `{'allowed_types': ['application/json', 'text/json']}` | services/playback_service.py:565 |
| `70602` | 413 | `upload playdata backup file size exceed` | `{'limit': '5MB'}` | services/playback_service.py:575 |
| `70603` | 415 | `upload playdata backup file decode error` | `{'allowed_encoding': 'UTF-8'}` | services/playback_service.py:587 |
| `70604` | 422 | `playdata backup file parse error` | - | services/playback_service.py:594 |
| `70605` | 422 | `playdata backup file json structure error` | - | services/playback_service.py:604 |
| `70606` | 422 | `import hit from json error` | - | services/playback_service.py:799 |
| `70607` | 422 | `import favorite from json error` | - | services/playback_service.py:853 |
| `70705` | 503 | `failed to start watcher.` | - | api/v1/admin/scan.py:94 |
| `70706` | 503 | `failed to stop watcher.` | - | api/v1/admin/scan.py:107 |
| `70801` | 409 | `lyric init is already running.` | - | api/v1/admin/lyric.py:92 |
| `70802` | 400 | `str(e)` | - | api/v1/admin/lyric.py:198 |
| `70803` | 409 | `lyric fetch is already running.` | - | api/v1/admin/lyric.py:150 |
| `70901` | 400 | `test err` | `{'a': 1, 'b': 2}` | api/v1/admin/__init__.py:29 |

---

## 四、约定与注意事项

### 1. 成功与错误的结构差异

- 成功响应：`{code: 200, msg: "ok", data: ...}`
- 错误响应：`{code, msg, detail, traceId}`，**没有 `data`**，前端需按 `code !== 200` 分支后再取 `detail`。

### 2. 新增错误码的流程

1. 在所属段位内取下一个未使用的码；
2. `raise BusinessException(code=..., msg=..., detail=..., status_code=...)`，`msg` 用英文小写描述，
   `detail` 携带可定位的参数（如 `{"track_id": 12}`）；
3. 前端在 `errors.biz.<code>` 补文案，未命中的码会回退到通用提示。

### 3. 前端映射建议

- 以 `code` 为主键映射文案，`httpStatus` 仅用于粗粒度分支（如 401 跳登录）；
- 未识别的 `code` 直接展示通用兜底文案，不要展示后端 `msg`；
- 排障时把 `traceId` 一并输出，后端日志按同一值检索。

### 4. 已知遗留

- 同一 code 对应多条 msg 的情况：已全部清零。
- `app/api/v1/admin/__init__.py:29` 的 `70901 / test err` 是调试接口，上线前应删除。
- 项目当前没有 WebSocket 端点。若将来新增，需单独约定 `WebSocketRequestValidationError` 的处理：
  FastAPI 默认只以 close code `1008` 断开连接，不带业务码、字段明细与 `traceId`，与本文件的 HTTP 包络无关。

---

## 五、维护方式

本清单由 AST 扫描生成，不是手工维护的表：

1. 扫描 `app/` 下所有 `raise BusinessException(...)`，取 `code` / `msg` / `detail` / `status_code` 四个关键字实参；
   `status_code` 缺省时按 `400` 计（`BusinessException.__init__` 默认值）。
2. 系统级响应来自 `app/core/exceptions.py` 的四个处理器 + `app/core/middleware.py` 的扫描锁，需人工核对。
3. 同源数据见 `tools/error_responses.csv`（列：module / source_type / code / http_status / msg / detail / file / line / note），
   该目录在 `.gitignore` 中，属于本地生成物。
