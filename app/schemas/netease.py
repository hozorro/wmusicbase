# -*- encoding: utf-8 -*-
'''
@File      :   netease.py
@Time      :   2025/01/01 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   netease playlist import schemas
'''


from pydantic import BaseModel, Field
from datetime import datetime


# ============ Netease Playlist Fetch ============

class NeteaseFetchRequest(BaseModel):
    '''fetch playlist request'''
    playlist_id: int | None = Field(None, description='Netease playlist id')
    share_text: str | None = Field(None, description='Netease share text with short url')


class NeteaseTrackInfo(BaseModel):
    '''netease track info'''
    id: int = Field(..., description='Netease track id')
    name: str = Field(..., description='Track name (full name)')
    mainTitle: str | None = Field(None, description='Main title (without additional info)')
    artists: list[str] = Field(default_factory=list, description='Artist names')
    album: str = Field(default='', description='Album name')
    duration: int = Field(0, description='Duration in milliseconds')


class NeteasePlaylistResponse(BaseModel):
    '''netease playlist info response'''
    id: int = Field(..., description='Netease playlist id')
    name: str = Field(..., description='Playlist name')
    coverImgUrl: str = Field(default='', description='Cover image URL')
    trackCount: int = Field(0, description='Total track count')
    tracks: list[NeteaseTrackInfo] = Field(default_factory=list, description='Track list')


# ============ Netease Match ============

class NeteaseMatchTrackItem(BaseModel):
    '''single track item for matching'''
    name: str = Field(..., description='Track name (full name)')
    mainTitle: str | None = Field(None, description='Main title (without additional info)')
    artists: list[str] = Field(default_factory=list, description='Artist names')
    album: str = Field(default='', description='Album name')


class NeteaseMatchRequest(BaseModel):
    '''match request'''
    tracks: list[NeteaseMatchTrackItem] = Field(..., description='Tracks to match')


class NeteaseMatchCandidate(BaseModel):
    '''matched local track candidate'''
    track_id: int = Field(..., description='Local track id')
    title: str = Field(..., description='Track title')
    artists: list[str] = Field(default_factory=list, description='Artist names')
    album: str = Field(default='', description='Album title')
    duration: float = Field(0, description='Duration in seconds')
    cover_art_hash: str | None = Field(None, description='Cover art hash')


class NeteaseMatchResult(BaseModel):
    '''single track match result'''
    netease_index: int = Field(..., description='Index in the original netease track list')
    netease_name: str = Field(..., description='Netease track name')
    netease_artists: list[str] = Field(default_factory=list, description='Netease artist names')
    netease_album: str = Field(default='', description='Netease album name')
    candidates: list[NeteaseMatchCandidate] = Field(default_factory=list, description='Matched local track candidates')


class NeteaseUnmatchedItem(BaseModel):
    '''unmatched track item'''
    netease_index: int = Field(..., description='Index in the original netease track list')
    netease_name: str = Field(..., description='Netease track name')
    netease_artists: list[str] = Field(default_factory=list, description='Netease artist names')
    netease_album: str = Field(default='', description='Netease album name')


class NeteaseMatchResponse(BaseModel):
    '''match response'''
    matched: list[NeteaseMatchResult] = Field(default_factory=list, description='Matched tracks')
    unmatched: list[NeteaseUnmatchedItem] = Field(default_factory=list, description='Unmatched tracks')
    total: int = Field(0, description='Total tracks')
    matched_count: int = Field(0, description='Matched count')
    unmatched_count: int = Field(0, description='Unmatched count')


# ============ Netease Create Playlist ============

class NeteaseCreateRequest(BaseModel):
    '''create playlist request'''
    title: str = Field(..., min_length=1, max_length=100, description='Playlist title')
    comment: str | None = Field(None, max_length=255, description='Playlist comment')
    cover_url: str | None = Field(None, description='Cover image URL to download')
    tracks: list[int] = Field(..., description='Local track ids in order')


class NeteaseCreateResponse(BaseModel):
    '''create playlist response'''
    id: int = Field(..., description='Playlist id')
    title: str = Field(..., description='Playlist title')
    cover_art_hash: str | None = Field(None, description='Cover art hash')
    track_count: int = Field(0, description='Track count')
    created_at: datetime = Field(..., description='Created at')
