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

# request
class UpdateVersion(BaseModel):
    id: str
    use_apev2: bool

class UpdateVerionList(BaseModel):
    items: list[UpdateVersion]

class UpdateMetaTags(MetaInfo):    # multi tags
    id: str

class UpdateMetaTagsList(BaseModel):
    items: list[UpdateMetaTags]

class UpdateMetaTagList(BaseModel): # single tag
    items: list[int]
    field: str
    value: str | int | list[str]

class CreateArchive(BaseModel):
    items: list[str]
    playlist: str | None

class CreateFingerprint(BaseModel):
    filename: str
    session_id: str

# responses
class FileInfoListResponse(RootModel):
    root: list[FileInfo]

class ArchiveResponse(BaseModel):
    archived: bool

class MatchAcoustResponse(BaseModel):
    matched_list: list[AcoustInfo]
    
class PlaylistJsonListResponse(BaseModel):
    playlists: list[PlaylistJsonInfo]