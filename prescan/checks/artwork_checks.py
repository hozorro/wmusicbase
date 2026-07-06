# -*- encoding: utf-8 -*-
'''
@File      :   artwork_checks.py
@Desc      :   Cover art and artist image checks
'''


from prescan.checks.base import BaseCheck, Issue, register_check
from prescan.models import InsTrack, InsArtist
from sqlalchemy import select


@register_check
class MissingEmbeddedCoverCheck(BaseCheck):
    name = 'missing_embedded_cover'
    description = '音频文件没有嵌入封面'

    def run(self) -> list[Issue]:
        tracks = self.session.execute(
            select(InsTrack).where(
                InsTrack.has_cover_art == False,
                InsTrack.parse_error == False
            )
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='warning', entity_type='track',
                entity_id=t.id, file_path=t.file_path,
                message=f'缺少嵌入封面: {t.title or t.file_name}',
            )
            for t in tracks
        ]


@register_check
class MissingArtistImageCheck(BaseCheck):
    name = 'missing_artist_image'
    description = '艺术家目录缺少 face.jpg'

    def run(self) -> list[Issue]:
        artists = self.session.execute(
            select(InsArtist).where(InsArtist.has_face_jpg == False)
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='warning', entity_type='artist',
                entity_id=a.id, file_path=a.dir_path,
                message=f'艺术家缺少 face.jpg: {a.name}',
            )
            for a in artists
        ]
