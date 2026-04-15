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
from mutagen.id3 import ID3, TIT2, TALB, TPE1, TPE2, TDRC, TCON, TXXX, UFID, APIC
from mutagen.flac import FLAC, Picture
from .common import parse_year
from typing import Any

BITRATE_MODES= {
    1: 'VBR',
    2: 'CBR',
    3: 'ABR',
}
# ID3 raw tag code and target field mapping
tag_mapping ={
    'TIT2': 'title',
    'TALB': 'album',
    'TPE1': 'artists',
    'TPE2': 'albumartist',
    'TDRC': 'year',
    'TCON': 'genres',
    'TXXX:MusicBrainz Artist Id': 'mb_artistids',
    'TXXX:MusicBrainz Album Id': 'mb_albumid',
    'TXXX:MusicBrainz Album Artist Id': 'mb_albumartistid',
    'UFID:http://musicbrainz.org': 'mb_trackid',
    'TXXX:Acoustid Id': 'acoustid_id'
}

def compute_file_hash(file_path: str | Path) -> str:
    '''compute file hash'''
    stat = Path(file_path).stat()
    size = stat.st_size
    mtime = int(stat.st_mtime)
    raw = f'{str(file_path)}{size}{mtime}'.encode('utf-8')
    return hashlib.sha256(raw).hexdigest(), size, mtime

def decode_tag_value(raw_value: Any, encoding: int) -> str:
    '''decode raw tag text to utf-8 str, according to encoding'''
    decoded_str = ''
    try:
        if encoding == 0:   # LATIN1
            # encode to bytes and decode to gb18030, transform to utf-8 finally
            if isinstance(raw_value, str):
                decoded_str = raw_value.encode('latin1', errors='ignore').decode('gb18030', errors='ignore')
            else:
                decoded_str = bytes(raw_value).decode('gb18030', errors='ignore')
        elif encoding == 1:  # UTF-16
            decoded_str = bytes(raw_value).decode('utf-16', errors='ignore')
        elif encoding == 2:  # UTF-16BE
            decoded_str = bytes(raw_value).decode('utf-16be', errors='ignore')
        elif encoding == 3:  # UTF-8
            decoded_str = bytes(raw_value).decode('utf-8', errors='ignore')
        else:
            decoded_str = str(raw_value, errors='ignore')
    except Exception:
        decoded_str = str(raw_value)
    # strip and transform to utf-8 finally
    return decoded_str.strip().encode('utf-8', errors='ignore').decode('utf-8')
def parse_metadata(file_path: str | Path) -> dict[str, Any]:
    # initial result
    result = {
        'title': '',
        'album': '',
        'artists': [],      # list type
        'albumartist': [],  # list type
        'year': 0,          # int type
        'genres': [],       # list type
        'duration': 0.0,    # float type
        'bitrate': 0,       # int type
        'bitrate_mode': '',
        'mb_artistids': [], # list type
        'mb_albumid': '',
        'mb_albumartistid': [], # list type
        'mb_trackid': '',
        'acoustid_id': ''
    }

    # when file is not exists/not music file/parse error, return initial result
    try:
        # 1. get basic physical info(length, bitrate, bitrate mode) from audio.info of audio file, no encoding problem
        audio = MutagenFile(file_path, easy=True)
        if audio and audio.info:
            result['duration'] = getattr(audio.info, 'length', 0.0)
            result['bitrate'] =getattr(audio.info, 'bitrate', 0) // 1000
            result['bitrate_mode'] = BITRATE_MODES.get(getattr(audio.info, 'bitrate_mode', '').__str__(), '')
        # 2. extract raw ID3 tags, including text and encoding
        id3_tags = ID3(file_path)
    except Exception:
        raise Exception(f"Failed to parse metadata for {file_path}")

    # list type fields
    LIST_TYPE_FIELDS = ['artists', 'albumartist', 'genres', 'mb_artistids', 'mb_albumartistid']
    
    for id3_tag_name, target_field in tag_mapping.items():
        if id3_tag_name not in id3_tags:
            continue
        
        tag_obj = id3_tags.get(id3_tag_name)
        if id3_tag_name == 'UFID:http://musicbrainz.org':
            result[target_field] = getattr(tag_obj, 'data', '').decode('utf-8', errors='ignore')
        else:
            raw_text_list = getattr(tag_obj, 'text', []) # raw data is always a list
            if not raw_text_list:
                continue

            if target_field in LIST_TYPE_FIELDS:
                decoded_list: list[str] = []
                for single_raw_val in raw_text_list:
                    decoded_val = decode_tag_value(single_raw_val, tag_obj.encoding)
                    if decoded_val:
                        decoded_list.append(decoded_val)
                result[target_field] = list(set(decoded_list))  # remove duplicate values
            else:
                first_raw_val = raw_text_list[0]
                decoded_text = decode_tag_value(first_raw_val, tag_obj.encoding)
                if target_field == 'year': 
                    # date tag in ID3 tag is various format, so we need to parse it to only reserve year and transform to int
                    result[target_field] = parse_year(decoded_text)
                else:
                    result[target_field] = decoded_text

    # padding fields
    if len(result['mb_artistids']) < len(result['artists']):
        result['mb_artistids'].extend([None] * (len(result['artists']) - len(result['mb_artistids'])))
    if len(result['mb_albumartistid']) < len(result['albumartist']):
        result['mb_albumartistid'].extend([None] * (len(result['albumartist']) - len(result['mb_albumartistid'])))

    return result
def write_metadata(file_path: str | Path, meta: dict[str, Any]) -> None:
    if Path(file_path).exists():
        try:
            if Path(file_path).suffix.lower() == '.mp3':
                audio = ID3(file_path)
                title = meta.get('title', '')
                if title:
                    audio['TIT2'] = TIT2(encoding=3, text=[title])
                album = meta.get('album', '')
                if album:
                    audio['TALB'] = TALB(encoding=3, text=[album])
                artists = meta.get('artists', [])
                if artists:
                    audio['TPE1'] = TPE1(encoding=3, text=artists)
                albumartist = meta.get('albumartist', [])
                if albumartist:
                    audio['TPE2'] = TPE2(encoding=3, text=albumartist)
                year = meta.get('year', 0)
                if year:
                    audio['TDRC'] = TDRC(encoding=3, text=[str(year)])
                genres = meta.get('genres', [])
                if genres:
                    audio['TCON'] = TCON(encoding=3, text=genres)
                mb_artistids = meta.get('mb_artistids', [])
                if mb_artistids:
                    audio['TXXX:MusicBrainz Artist Id'] = TXXX(encoding=3, desc='MusicBrainz Artist Id', text=mb_artistids)
                mb_albumid = meta.get('mb_albumid', '')
                if mb_albumid:
                    audio['TXXX:MusicBrainz Album Id'] = TXXX(encoding=3, desc='MusicBrainz Album Id', text=[mb_albumid])
                mb_albumartistid = meta.get('mb_albumartistid', [])
                if mb_albumartistid:
                    audio['TXXX:MusicBrainz Album Artist Id'] = TXXX(encoding=3, desc='MusicBrainz Album Artist Id', text=mb_albumartistid)
                mb_trackid = meta.get('mb_trackid', '')
                if mb_trackid:
                    audio['UFID:http://musicbrainz.org'] = UFID(owner='http://musicbrainz.org', data=mb_trackid.encode('utf-8'))
                acoustid_id = meta.get('acoustid_id', '')
                if acoustid_id:
                    audio['TXXX:Acoustid Id'] = TXXX(encoding=3, desc='Acoustid Id', text=[acoustid_id])
                cover_art_data = meta.get('cover_art_data', None)
                if cover_art_data and type(cover_art_data) == bytes:
                    audio['APIC'] = APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_art_data)
                audio.save()
            elif Path(file_path).suffix.lower() == '.flac':
                audio = FLAC(file_path)
                title = meta.get('title', '')
                if title:
                    audio['title'] = title
                album = meta.get('album', '')
                if album:
                    audio['album'] = album
                artists = meta.get('artists', [])
                if artists:
                    audio['artist'] = artists
                albumartist = meta.get('albumartist', [])
                if albumartist:
                    audio['albumartist'] = albumartist
                year = meta.get('year', 0)
                if year:
                    audio['date'] = str(year)
                genres = meta.get('genres', [])
                if genres:
                    audio['genre'] = genres
                # mb tags support?
                cover_art_data = meta.get('cover_art_data', None)
                if cover_art_data and type(cover_art_data) == bytes:
                    picture = Picture()
                    picture.data = cover_art_data
                    picture.mime = 'image/jpeg'
                    picture.type = 3
                    picture.desc = 'Cover'
                    audio.add_picture(picture)
                audio.save()
        except Exception:
            raise Exception('Update metadata failed')
    else:
        raise FileNotFoundError
def easy_metadata(file_path: Path | str) -> dict[str, Any] | None:
    '''
    extract metadata from audio file, without encoding transform
    '''
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
            title = file_path.stem # use file name as title if no title tag
        
        artists = _get_list('artist')
        mb_artistids = _get_list('musicbrainz_artistid')
        if len(mb_artistids) < len(artists):
            mb_artistids.extend([None] * (len(artists) - len(mb_artistids)))
        
        albumartist = _get_list('albumartist')
        mb_albumartistid = _get_list('musicbrainz_albumartistid')
        if len(mb_albumartistid) < len(albumartist):
            mb_albumartistid.extend([None] * (len(albumartist) - len(mb_albumartistid)))
        
        bitrate_mode = BITRATE_MODES.get(getattr(audio.info, 'bitrate_mode', None), None)

        return {
            'title': title,
            'artists': list(set(artists)),  # remove duplicate artists
            'mb_artistids': list(set(mb_artistids)),  # remove duplicate mb_artistids
            'album': _get_first(audio.get('album', [''])),
            'mb_albumid': _get_first(audio.get('musicbrainz_albumid', [''])),
            'albumartist': list(set(albumartist)),  # remove duplicate albumartists 
            'mb_albumartistid': list(set(mb_albumartistid)),  # remove duplicate mb_albumartistid
            'year': parse_year(_get_first(audio.get('date', ['']))),
            'genres': list(set(_get_list('genre'))),  # remove duplicate genres
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
    '''only compute the SHA1 value of the embedded cover art, not return image data'''
    try:
        audio = MutagenFile(file_path)
        
        # handle mp3 file
        if hasattr(audio, 'tags') and hasattr(audio.tags, 'keys'):
            apic_keys = [key for key in audio.tags.keys() if key.startswith('APIC:')]
            if apic_keys:
                return hashlib.sha1(audio.tags[apic_keys[0]].data).hexdigest()
        # handle flac file
        elif hasattr(audio, 'pictures') and len(audio.pictures) > 0:
            return hashlib.sha1(audio.pictures[0].data).hexdigest()
    except Exception as e:
        print(f'Error extracting cover art for {file_path}: {e}')
    return None

def extract_embedded_artwork(file_path: str) -> bytes | None:
    '''extract the first embedded artwork bytes data from audio file'''
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

def download_cover_art(release_id) -> bytes | None:
    '''download cover art from coverartarchive.org'''
    import requests
    from app.core.config import settings
    cover_art_url = f'{settings.PROXY_API_URL}/cover/{release_id}?api_key={settings.PROXY_API_KEY}'
    try:
        resp = requests.get(cover_art_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        return resp.content
    except Exception:
        return None