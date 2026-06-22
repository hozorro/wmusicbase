# -*- encoding: utf-8 -*-
'''
@File      :   structure_checks.py
@Desc      :   Directory structure compliance checks
'''


from prescan.checks.base import BaseCheck, Issue, register_check
from prescan.models import InsTrack
from sqlalchemy import select

VALID_AREAS = {'Chinese', 'Foreign'}
VALID_CHAR_RANGES = {'A-G', 'H-N', 'O-T', 'U-Z', 'Z_'}
EXPECTED_DIR_LEVEL = 5  # area/char_range/artist/album/file


@register_check
class InvalidDirLevelCheck(BaseCheck):
    name = 'invalid_dir_level'
    description = '文件不在预期的5层目录结构中'

    def run(self) -> list[Issue]:
        tracks = self.session.execute(
            select(InsTrack).where(
                InsTrack.dir_level != EXPECTED_DIR_LEVEL,
                InsTrack.parse_error == False
            )
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='info', entity_type='directory',
                entity_id=t.id, file_path=t.file_path,
                message=f'目录层级异常 (期望{EXPECTED_DIR_LEVEL}层, 实际{t.dir_level}层): {t.file_path}',
            )
            for t in tracks
        ]


@register_check
class InvalidAreaCheck(BaseCheck):
    name = 'invalid_area'
    description = '第一层目录不是 Chinese 或 Foreign'

    def run(self) -> list[Issue]:
        tracks = self.session.execute(
            select(InsTrack).where(
                InsTrack.dir_area.notin_(VALID_AREAS),
                InsTrack.dir_area.isnot(None),
                InsTrack.parse_error == False
            )
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='info', entity_type='directory',
                entity_id=t.id, file_path=t.file_path,
                message=f'无效的区域目录 "{t.dir_area}": {t.file_path}',
            )
            for t in tracks
        ]


@register_check
class InvalidCharRangeCheck(BaseCheck):
    name = 'invalid_char_range'
    description = '第二层目录不在合法范围中'

    def run(self) -> list[Issue]:
        tracks = self.session.execute(
            select(InsTrack).where(
                InsTrack.dir_char_range.notin_(VALID_CHAR_RANGES),
                InsTrack.dir_char_range.isnot(None),
                InsTrack.parse_error == False
            )
        ).scalars().all()
        return [
            Issue(
                check_name=self.name, severity='info', entity_type='directory',
                entity_id=t.id, file_path=t.file_path,
                message=f'无效的字母范围目录 "{t.dir_char_range}": {t.file_path}',
            )
            for t in tracks
        ]
