# -*- encoding: utf-8 -*-
'''
@File      :   metadata.py
@Time      :   2025/10/19 22:51:03
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   parse audio file metadata
'''


import hashlib
from pathlib import Path
from mutagen import File as MutagenFile
from typing import Any

BITRATE_MODES= {
    1: 'VBR',
    2: 'CBR',
    3: 'ABR',
}
def parse_year(date_str: str) -> int | None:
    '''从date字符串提取年份'''
    if not date_str: return None
    year_str = ''.join(filter(str.isdigit, date_str[:4]))
    return int(year_str) if year_str.isdigit() and len(year_str) == 4 else None

def extract_metadata(file_path: Path) -> dict[str, Any] | None:
    '''提取音频文件的元数据'''
    try:
        audio = MutagenFile(file_path, easy=True)
        if not audio or not hasattr(audio, 'info') or not audio.info:
            return None
        
        def _get_first(lst: list[str], default: str = '') -> str:
            return lst[0] if lst else default
        
        def _get_list(tag: str) -> list[str]:
            return audio.get(tag, [])
        
        title = _get_first(audio.get('title', ['']))
        if not title:
            title = file_path.stem # 无标题时使用文件名
        
        artists = _get_list('artist')
        mb_artistids = _get_list('musicbrainz_artistid')
        if len(mb_artistids) < len(artists):
            mb_artistids.extend([None] * (len(artists) - len(mb_artistids)))
        
        bitrate_mode = BITRATE_MODES.get(getattr(audio.info, 'bitrate_mode', None), None)

        return {
            'title': title,
            'artists': artists,
            'mb_artistids': mb_artistids,
            'album': _get_first(audio.get('album', [''])),
            'mb_albumid': _get_first(audio.get('musicbrainz_albumid', [''])),
            'albumartist': _get_list('albumartist'),
            'mb_albumartistid': _get_list('musicbrainz_albumartistid'),
            'year': parse_year(_get_first(audio.get('date', ['']))),
            'genres': _get_list('genre'),
            'duration': getattr(audio.info, 'length', 0.0),
            'bitrate': getattr(audio.info, 'bitrate', 0) // 1000,
            'bitrate_mode': bitrate_mode,
            'acoustid_id': _get_first(audio.get('acoustid_id', [''])),
            'mb_trackid': _get_first(audio.get('musicbrainz_trackid', [''])),
        }
    except Exception as e:
        print(f'Error parsing metadata for {file_path}: {e}')
        return None
    
def extract_cover_art_hash(file_path: Path) -> str | None:
    '''仅计算嵌入封面的SHA1值，不返回图片数据'''
    try:
        audio = MutagenFile(file_path)
        
        # 处理MP3文件
        if hasattr(audio, 'tags') and hasattr(audio.tags, 'keys'):
            apic_keys = [key for key in audio.tags.keys() if key.startswith('APIC:')]
            if apic_keys:
                return hashlib.sha1(audio.tags[apic_keys[0]].data).hexdigest()
        # 处理flac文件
        elif hasattr(audio, 'pictures') and len(audio.pictures) > 0:
            return hashlib.sha1(audio.pictures[0].data).hexdigest()
    except Exception as e:
        print(f'Error extracting cover art for {file_path}: {e}')
    return None

def extract_embedded_artwork(file_path: str) -> bytes | None:
    '''从音乐文件中提取第一张嵌入封面的原始字节数据'''
    try:
        audio = MutagenFile(file_path)
        if hasattr(audio, 'tags') and hasattr(audio.tags, 'keys'):
            apic_keys = [key for key in audio.tags.keys() if key.startswith('APIC:')]
            if apic_keys:
                return audio.tags[apic_keys[0]].data
        elif hasattr(audio, 'pictures') and len(audio.pictures) > 0:
            return audio.pictures[0].data
    except Exception as e:
        print(f'Failed to extract cover art from {file_path}: {e}')
    return None