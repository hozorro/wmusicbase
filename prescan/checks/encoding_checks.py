# -*- encoding: utf-8 -*-
'''
@File      :   encoding_checks.py
@Desc      :   Encoding / mojibake detection checks
'''


import re
from prescan.checks.base import BaseCheck, Issue, register_check
from prescan.models import InsTrack, InsArtist, InsAlbum
from sqlalchemy import select

# common mojibake patterns
_MOJIBAKE_PATTERNS = [
    re.compile(r'\ufffd'),              # UTF-8 replacement character
    re.compile(r'Â[\x80-\xbf]'),        # double-encoded UTF-8 (Latin1 read of UTF-8)
    re.compile(r'Ã[\x80-\xbf]'),        # Latin1 misread of UTF-8
    re.compile(r'ï¿½'),                  # UTF-8 BOM / replacement in Latin1
    re.compile(r'[\xc0-\xc1][\x80-\xbf]'),  # overlong UTF-8 sequences
]


def _has_mojibake(text: str) -> bool:
    '''check if a string contains potential mojibake characters'''
    if not text:
        return False
    for pattern in _MOJIBAKE_PATTERNS:
        if pattern.search(text):
            return True
    return False


@register_check
class MojibakeDetectionCheck(BaseCheck):
    name = 'mojibake_detected'
    description = '元数据中检测到潜在乱码'

    def run(self) -> list[Issue]:
        issues: list[Issue] = []

        # check track titles
        tracks = self.session.execute(
            select(InsTrack).where(InsTrack.parse_error == False)
        ).scalars().all()
        for t in tracks:
            if _has_mojibake(t.title):
                issues.append(Issue(
                    check_name=self.name, severity='error', entity_type='track',
                    entity_id=t.id, file_path=t.file_path,
                    message=f'标题疑似乱码: "{t.title}"',
                ))

        # check artist names
        artists = self.session.execute(select(InsArtist)).scalars().all()
        for a in artists:
            if _has_mojibake(a.name):
                issues.append(Issue(
                    check_name=self.name, severity='error', entity_type='artist',
                    entity_id=a.id, file_path=a.dir_path,
                    message=f'艺术家名疑似乱码: "{a.name}"',
                ))

        # check album titles
        albums = self.session.execute(select(InsAlbum)).scalars().all()
        for album in albums:
            if _has_mojibake(album.title):
                issues.append(Issue(
                    check_name=self.name, severity='error', entity_type='album',
                    entity_id=album.id, file_path=album.dir_path,
                    message=f'专辑名疑似乱码: "{album.title}"',
                ))

        return issues
