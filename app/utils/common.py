# -*- encoding: utf-8 -*-
'''
@File      :   common.py
@Time      :   2025/11/06 16:26:20
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   common tools
'''


import re
from pathlib import Path

def normalize_music_filename(filename: str) -> str:
    '''lowercase only the extension; keep the stem and any parent dirs untouched

    Track.path is case-sensitive (uq_track_path), so the same song stored as
    'Song.MP3' and 'Song.mp3' would become two different records.
    '''
    path = Path(filename)
    suffix = path.suffix
    if not suffix:
        return filename
    return str(path.with_suffix(suffix.lower()))

def parse_year(date_str: str | None) -> int | None:
    '''parse year from date string; None/empty is a valid "no date" input'''
    if not date_str: return None
    year_str = ''.join(filter(str.isdigit, date_str[:4]))
    return int(year_str) if year_str.isdigit() and len(year_str) == 4 else None
        
def parse_multiple_value(value: str | None) -> list[str] | None:
    '''parse multiple value, return list; None/empty returns None'''
    sep = r'[;,，&|/\\]'
    return list(map(lambda x: x.strip(), re.split(sep, value))) if value else None

# Invalid folder name characters: < > : " / \ | ? *
_INVALID_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*]')
def sanitize_folder_name(name: str) -> str:
    '''
    sanitize folder name by replacing all invalid characters with '_'
    Windows invalid chars: < > : " / \\ | ? *
    Also handles trailing dots and spaces
    '''
    # replace all invalid characters
    result = _INVALID_CHARS_PATTERN.sub('_', name)
    # replace trailing dots and spaces
    result = re.sub(r'[. ]+$', '_', result)
    return result