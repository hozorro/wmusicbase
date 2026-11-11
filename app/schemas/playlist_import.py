# -*- encoding: utf-8 -*-
'''
@File      :   playlist_import.py
@Desc      :   schemas for importing a playlist json and matching tracks
'''


from typing import Literal
from pydantic import BaseModel, Field, field_validator

MatchLevel = Literal['path', 'exact', 'artist', 'title']
MatchBy = Literal['path', 'meta', 'none']


class PlaylistImportTrack(BaseModel):
    '''one track parsed from the uploaded playlist json'''
    title: str | None = Field(default=None, description='Track title')
    artists: list[str] = Field(default_factory=list, max_length=50, description='Artist names')
    album: str | None = Field(default=None, description='Album title')
    path: str | None = Field(default=None, description='Path relative to the music library root')

    @field_validator('title', 'album', 'path', mode='before')
    @classmethod
    def normalize_optional_text(cls, v):
        if not isinstance(v, str):
            return None
        return v.strip() or None

    @field_validator('artists', mode='before')
    @classmethod
    def normalize_artists(cls, v):
        if not isinstance(v, list):
            return []
        return [a.strip() for a in v if isinstance(a, str) and a.strip()][:50]


class PlaylistMatchRequest(BaseModel):
    '''tracks to be matched against the local music library'''
    tracks: list[PlaylistImportTrack] = Field(default_factory=list, max_length=1000)


class PlaylistMatchCandidate(BaseModel):
    '''a local track candidate, always carries the id used for creation'''
    track_id: int
    title: str
    artists: list[str] = Field(default_factory=list)
    album: str = ''
    path: str = ''
    match_level: MatchLevel = 'title'


class PlaylistTrackMatchResult(BaseModel):
    '''match result of one input track'''
    index: int
    source: PlaylistImportTrack
    match_by: MatchBy
    candidates: list[PlaylistMatchCandidate] = Field(default_factory=list)


class PlaylistMatchResponse(BaseModel):
    '''whole match result of an uploaded playlist'''
    total: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    results: list[PlaylistTrackMatchResult] = Field(default_factory=list)


class PlaylistCreateFromMatchRequest(BaseModel):
    '''create a playlist with ids picked from the match result, no re-matching'''
    title: str = Field(..., min_length=1, max_length=100, description='Playlist title')
    comment: str | None = Field(default=None, max_length=255, description='Playlist comment')
    track_ids: list[int] = Field(default_factory=list, max_length=1000, description='Ordered local track ids')

    @field_validator('title')
    @classmethod
    def validate_title(cls, v: str) -> str:
        title = v.strip()
        if not title:
            raise ValueError('playlist title must not be blank')
        return title

    @field_validator('comment', mode='before')
    @classmethod
    def normalize_comment(cls, v):
        if not isinstance(v, str):
            return None
        return v.strip() or None


class PlaylistCreateFromMatchResponse(BaseModel):
    '''creation result'''
    id: int
    title: str
    requested: int = 0
    added: int = 0
    ignored: int = 0
    detail: str = ''
