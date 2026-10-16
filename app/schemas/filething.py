# -*- encoding: utf-8 -*-
'''
@File      :   filething.py
@Time      :   2025/11/04 22:07:50
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   file treatment schemas
'''


from pydantic import BaseModel, RootModel
from typing import Optional

class GeneralOutPut(BaseModel):
    count: Optional[int]

# basic models
class FileBase(BaseModel):
    filename: str

class SessionBase(BaseModel):
    session_id: str

class SessionInfo(SessionBase):
    song_count: int
    created_at: float

class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]

class MetaInfoWithNoArt(BaseModel):
    title: str | None
    artists: list[str] | None
    album: str | None
    albumartist: list[str] | None
    year: int | None
    genres: list[str] | None
    mb_artistids: list[str | None] | None
    mb_albumartistid: list[str | None] | None
    mb_albumid: str | None
    mb_trackid: str | None
    acoustid_id: str | None

class MetaInfo(MetaInfoWithNoArt):
    cover_art_hash: str | None

class ParsedMeta(MetaInfoWithNoArt):
    path: str
    duration: float | None
    bitrate: int | None
    bitrate_mode: str | None
    # fingerprint: str | None
    # size: int | None
    # mtime: int | None

class PrimaryInfo(BaseModel):
    title: str | None
    artists: list[str] | None
    album: str | None
    year: int | None
    genres: list[str] | None

class AdditionalInfo(BaseModel):
    albumartist: list[str] | None
    cover_art_hash: str | None
    mb_artistids: list[str | None] | None
    mb_albumartistid: list[str | None] | None
    mb_albumid: str | None
    mb_trackid: str | None
    acoustid_id: str | None

class FileInfo(BaseModel):
    path: str
    file_type: str | None
    encoding: str | None
    version: list[str] | None
    meta_id3: PrimaryInfo | None
    meta_apev2: PrimaryInfo | None
    meta_additional: AdditionalInfo | None

class Fingerprint(BaseModel):
    fingerprint: str
    duration: float

class AcoustArtist(BaseModel):
    id: str
    name: str

class AcoustInfo(BaseModel):
    acoustid_id: str
    id: str
    title: str
    duration: float
    artists: list[AcoustArtist]
    release_id: str
    release_title: str
    release_year: int
    release_artists: list[AcoustArtist]
    release_country: str
    release_track_count: int
    score: float

class PlaylistJsonInfo(BaseModel):
    filename: str
    title: str
    username: str
    source: str
    time: str
    items: list[str]

# ======= check music file before upload =======
class MusicFile(BaseModel):
    '''Music file'''
    file_name: str  # File name
    stem: str       # File name without extension
    artists: list[str]
    title: str

class MatchedTrack(BaseModel):
    '''matched track'''
    file: MusicFile
    db_track_id: int
    db_title: str
    db_path: str
    db_artists: list[str]
    matched_artist: str

class UnmatchedFile(BaseModel):
    '''unmatched file'''
    file: MusicFile
    reason: str

# request
class UpdateVersion(BaseModel):
    id: str
    use_apev2: bool

class UpdateVerionList(BaseModel):
    items: list[UpdateVersion]

class UpdateMetaTags(MetaInfo):    # multi tags
    id: str
    use_matched_cover: bool | None = False

class UpdateMetaTagsList(BaseModel):
    batch_count: int
    items: list[UpdateMetaTags]

class UpdateMetaTagList(BaseModel): # single tag
    items: list[int]
    field: str
    value: str | int | list[str]

class CreateArchive(BaseModel):
    items: list[str]
    is_use_original_name: bool = False
    playlist: str | None = None

class DeleteStagingFiles(BaseModel):
    items: list[str]

class CreateFingerprint(BaseModel):
    filename: str
    session_id: str

class ScanOptions(BaseModel):
    is_incremental: bool

class CheckTrackFileRequest(BaseModel):
    list_text: str

# responses
class FileInfoListResponse(RootModel):
    root: list[FileInfo]

class ArchiveResponse(BaseModel):
    archived: bool

class MatchAcoustResponse(BaseModel):
    matched_list: list[AcoustInfo]
    
class PlaylistJsonListResponse(BaseModel):
    playlists: list[PlaylistJsonInfo]

class PlaylistBackupInfo(BaseModel):
    id: int
    title: str
    username: str
    tracks: list[dict[str, str | list[str]]]
    show: bool | None = False

class PlaylistBackupResponse(RootModel):
    root: list[PlaylistBackupInfo]

class CheckTrackFileResponse(BaseModel):
    total: int
    valid: int
    matched: list[MatchedTrack]
    unmatched: list[UnmatchedFile]
    
