# -*- encoding: utf-8 -*-
'''
@File      :   structure_checks.py
@Desc      :   Directory structure compliance checks
'''


from prescan.checks.base import BaseCheck, Issue, register_check, register_after_check
from prescan.models import InsTrack, InsArtist, ins_track_artists
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


@register_check
class MissingArtistFolderCheck(BaseCheck):
    name = 'missing_artist_folder'
    description = '艺术家没有以其名字命名的文件夹'

    def run(self) -> list[Issue]:
        artists = self.session.execute(
            select(InsArtist).where(
                (InsArtist.dir_path == '') | InsArtist.dir_path.is_(None),
            )
        ).scalars().all()

        return [
            Issue(
                check_name=self.name, severity='warning', entity_type='artist',
                entity_id=a.id, file_path=None,
                message=f'艺术家没有对应文件夹: {a.name}',
            )
            for a in artists
        ]


@register_after_check
class OrphanArtistFolderCheck(BaseCheck):
    name = 'orphan_artist_folder'
    description = '艺术家文件夹名没有匹配任何歌手'

    def run(self) -> list[Issue]:
        # 1. scan library directory structure to get all artist-level folders
        print(self.library_path)
        folder_names: set[str] = set()
        if not self.library_path.exists():
            return []
        for area_dir in self.library_path.iterdir():
            if not area_dir.is_dir():
                continue
            for range_dir in area_dir.iterdir():
                if not range_dir.is_dir():
                    continue
                for artist_dir in range_dir.iterdir():
                    if artist_dir.is_dir():
                        folder_names.add(artist_dir.name)
        print(f'第3层文件夹数量：{len(folder_names)}')

        # 2. get all artist names from database
        artist_names: set[str] = set()
        artists = self.session.execute(select(InsArtist.name)).scalars().all()
        artist_names.update(artists)

        # 3. find folders that don't match any artist
        orphan_folders = folder_names - artist_names

        return [
            Issue(
                check_name=self.name, severity='info', entity_type='directory',
                entity_id=None, file_path=None,
                message=f'未匹配歌手的艺术家文件夹: {name}',
            )
            for name in sorted(orphan_folders)
        ]


@register_after_check
class MissingArtistFolderTracksCheck(BaseCheck):
    name = 'missing_artist_folder_tracks'
    description = '没有对应文件夹的歌手及其曲目路径'

    def __init__(self, session, library_path):
        super().__init__(session, library_path)
        self._detail_rows: list[tuple[str, str, str]] = []  # (artist_name, track_title, file_path)

    def run(self) -> list[Issue]:
        artists = self.session.execute(
            select(InsArtist).where(
                (InsArtist.dir_path == '') | InsArtist.dir_path.is_(None),
            )
        ).scalars().all()

        self._detail_rows.clear()
        total_tracks = 0

        for artist in artists:
            tracks = self.session.execute(
                select(InsTrack).join(
                    ins_track_artists, InsTrack.id == ins_track_artists.c.track_id
                ).where(
                    ins_track_artists.c.artist_id == artist.id
                ).order_by(InsTrack.file_path)
            ).scalars().all()

            total_tracks += len(tracks)
            for t in tracks:
                self._detail_rows.append((artist.name, t.title or t.file_name, t.file_path))

        # terminal only shows statistics
        return [
            Issue(
                check_name=self.name, severity='warning', entity_type='artist',
                entity_id=None, file_path=None,
                message=f'{len(artists)} 位歌手没有文件夹, 共涉及 {total_tracks} 首曲目',
            )
        ]

    def export_csv(self, output_path) -> int:
        '''export artist-track detail to CSV'''
        import csv
        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['artist_name', 'track_title', 'file_path'])
            for row in self._detail_rows:
                writer.writerow(row)
        return len(self._detail_rows)
