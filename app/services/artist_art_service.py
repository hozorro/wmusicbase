# -*- encoding: utf-8 -*-
'''
@File      :   artist_art_service.py
@Time      :   2025/12/30 00:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   artist artwork folder management service
'''


import shutil
from pathlib import Path

# TODO: move these paths to settings for configurability
_ARTIST_COVER_SOURCE_ROOT = Path(r'D:\tmp\artist_covers\have_dir')
_ARTIST_COVER_DEST_ROOT = Path(r'H:\musiclibcorrect')


def get_folder_artist_arts(area: str, char_range: str) -> list[dict]:
    '''list all artists and their available cover art names in a given area/char_range'''
    iter_root = _ARTIST_COVER_SOURCE_ROOT / area / char_range
    results = []
    if not iter_root.exists():
        return results
    for dir in iter_root.iterdir():
        if not dir.is_dir():
            continue
        artist_name = dir.name
        artist_covers = [face.stem for face in dir.glob('*.jpg')]
        results.append({'name': artist_name, 'covers': artist_covers})
    return results


def get_folder_artist_art_file(area: str, char_range: str, artist_name: str, file_stem: str) -> Path:
    '''get the file path of a specific artist cover art'''
    return _ARTIST_COVER_SOURCE_ROOT / area / char_range / artist_name / f'{file_stem}.jpg'


def set_folder_artist_art(area: str, char_range: str, covers: list[dict[str, str]]) -> dict:
    '''copy selected artist cover arts to the destination music library'''
    exists = []
    no_dirs = []
    created = []
    for cover in covers:
        artist_name = cover['name']
        file_stem = cover['cover']
        src_path = _ARTIST_COVER_SOURCE_ROOT / area / char_range / artist_name / f'{file_stem}.jpg'
        dst_path = _ARTIST_COVER_DEST_ROOT / area / char_range / artist_name / 'face.jpg'

        if dst_path.exists():
            exists.append(artist_name)
        else:
            if not dst_path.parent.exists():
                dst_path.parent.mkdir(parents=True)
                no_dirs.append(artist_name)
            shutil.copy(str(src_path), str(dst_path))
            created.append(artist_name)
    return {
        'exists': exists,
        'created': created,
        'no_dirs': no_dirs,
        'total': len(exists) + len(created)
    }
