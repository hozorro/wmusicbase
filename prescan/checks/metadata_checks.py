# -*- encoding: utf-8 -*-
'''
@File      :   metadata_checks.py
@Desc      :   Metadata completeness and quality checks
'''


from prescan.checks.base import BaseCheck, Issue, register_check
from prescan.models import InsTrack, ins_track_artists, ins_track_genres
from sqlalchemy import select, func


@register_check
class MissingTitleCheck(BaseCheck):
    name = 'missing_title'
    description = '曲目缺少标题'

    def run(self) -> list[Issue]:
        tracks = self.session.execute(
            select(InsTrack).where(
                (InsTrack.title == '') | InsTrack.title.is_(None),
                InsTrack.parse_error == False
            )
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='error', entity_type='track',
                entity_id=t.id, file_path=t.file_path,
                message=f'曲目缺少标题: {t.file_name}',
            )
            for t in tracks
        ]


@register_check
class MissingArtistCheck(BaseCheck):
    name = 'missing_artist'
    description = '曲目没有关联艺术家'

    def run(self) -> list[Issue]:
        # tracks with no artist association
        subq = select(ins_track_artists.c.track_id).distinct().subquery()
        tracks = self.session.execute(
            select(InsTrack).where(
                InsTrack.id.notin_(select(subq)),
                InsTrack.parse_error == False
            )
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='error', entity_type='track',
                entity_id=t.id, file_path=t.file_path,
                message=f'曲目没有关联艺术家: {t.title or t.file_name}',
            )
            for t in tracks
        ]


@register_check
class MissingAlbumCheck(BaseCheck):
    name = 'missing_album'
    description = '曲目缺少专辑信息'

    def run(self) -> list[Issue]:
        tracks = self.session.execute(
            select(InsTrack).where(
                InsTrack.album_id.is_(None),
                InsTrack.parse_error == False
            )
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='warning', entity_type='track',
                entity_id=t.id, file_path=t.file_path,
                message=f'曲目缺少专辑信息: {t.title or t.file_name}',
            )
            for t in tracks
        ]


@register_check
class MissingGenreCheck(BaseCheck):
    name = 'missing_genre'
    description = '曲目没有关联流派'

    def run(self) -> list[Issue]:
        subq = select(ins_track_genres.c.track_id).distinct().subquery()
        tracks = self.session.execute(
            select(InsTrack).where(
                InsTrack.id.notin_(select(subq)),
                InsTrack.parse_error == False
            )
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='warning', entity_type='track',
                entity_id=t.id, file_path=t.file_path,
                message=f'曲目没有关联流派: {t.title or t.file_name}',
            )
            for t in tracks
        ]


@register_check
class ShortTrackCheck(BaseCheck):
    name = 'short_track'
    description = '曲目时长过短 (< 10秒)'

    def run(self) -> list[Issue]:
        tracks = self.session.execute(
            select(InsTrack).where(
                InsTrack.duration < 10.0,
                InsTrack.duration > 0,
                InsTrack.parse_error == False
            )
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='warning', entity_type='track',
                entity_id=t.id, file_path=t.file_path,
                message=f'曲目时长过短: {t.duration:.1f}s - {t.title or t.file_name}',
            )
            for t in tracks
        ]


@register_check
class ParseErrorCheck(BaseCheck):
    name = 'parse_error'
    description = '文件元数据解析失败'

    def run(self) -> list[Issue]:
        tracks = self.session.execute(
            select(InsTrack).where(InsTrack.parse_error == True)
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='error', entity_type='track',
                entity_id=t.id, file_path=t.file_path,
                message=f'元数据解析失败: {t.file_name}',
                detail=t.error_message,
            )
            for t in tracks
        ]
