# -*- encoding: utf-8 -*-
'''
@File      :   audiofile.py
@Time      :   2025/11/06 16:12:29
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   parse audio property
'''


from pathlib import Path
from mutagen import File as MutagenFile
from mutagen.id3 import ID3, Encoding
from mutagen.apev2 import APEv2, APENoHeaderError
from app.schemas.filething import FileInfo
from .metadata import decode_tag_value, parse_metadata, easy_metadata, write_metadata, extract_cover_art_hash
from .common import decode_object, parse_year, parse_multiple_value

_KEY_MAP = {
    'artists': 'artist',
    'genres': 'genre',
    'mb_artistids': 'musicbrainz_artistid',
    'mb_albumartistid': 'musicbrainz_albumartistid',
    'mb_albumid': 'musicbrainz_albumid',
    'mb_trackid': 'musicbrainz_trackid',
}

_ENCODING_MAP = {
    0: 'latin-1',
    1: 'utf-16',
    2: 'utf-16-be',
    3: 'utf-8',
}

_APEv2_KEY_MAP = {  # APEv2 key -> ID3v2 key
    'Title': 'TIT2',
    'Artist': 'TPE1',
    'Album': 'TALB',
    'Year': 'TDRC',
    'Genre': 'TCON',
}

class AudioMeta:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.meta_encoding = None
        self.meta_version = []
        self._meta_data = None

        self.init_version()

    def init_version(self):
        self.meta_version = []
        try:
            tags = ID3(self.file_path)
            id3_version = tags.version
            version = 'ID3v' + '.'.join(map(str, id3_version))
            self.meta_version.append(version)

            keys = list(tags.keys())
            if keys:
                encoding = tags[keys[0]].encoding
                self.meta_encoding = _ENCODING_MAP.get(encoding, 'unknown')
                for key in keys:
                    if tags[key].encoding != encoding:  # 忽略编码不一致的标签
                        self.meta_encoding = 'mixed'
                        break
        except:
            pass

        try:
            _ = APEv2(self.file_path)
            self.meta_version.append('APEv2')
        except APENoHeaderError:
            pass

    @property
    def meta_data(self):  
        if self._meta_data is not None:
            return self._meta_data  
        metadata_primary = {
            'title': '',
            'artists': [],
            'album': '',
            'year': None,
            'genres': [],
        }
        metadata_additional = {
            'albumartist': [],
            'cover_art_hash': None,
            'mb_artistids': [],
            'mb_albumartistid': [],
            'mb_albumid': '',
            'mb_trackid': '',
            'acoustid_id': '',
        }
        try:
            if Path(self.file_path).suffix.lower() == ".mp3":
                meta = parse_metadata(Path(self.file_path))
            else:
                meta = easy_metadata(Path(self.file_path))
            metadata_primary['title'] = meta.get('title', '')
            metadata_primary['artists'] = meta.get('artists', [])
            metadata_primary['album'] = meta.get('album', '')
            metadata_primary['year'] = meta.get('year', 0)
            metadata_primary['genres'] = meta.get('genres', [])
            metadata_additional['albumartist'] = meta.get('albumartist', [])
            metadata_additional['cover_art_hash'] = extract_cover_art_hash(self.file_path)
            metadata_additional['mb_artistids'] = meta.get('mb_artistids', [])
            metadata_additional['mb_albumartistid'] = meta.get('mb_albumartistid', [])
            metadata_additional['mb_albumid'] = meta.get('mb_albumid', '')
            metadata_additional['mb_trackid'] = meta.get('mb_trackid', '')
            metadata_additional['acoustid_id'] = meta.get('acoustid_id', '')
        except Exception:
            pass
        return {'primary': metadata_primary, 'additional': metadata_additional}
    
    @property
    def apev2_data(self):
        meta = {
            'title': None,
            'artists': [],
            'album': None,
            'year': None,
            'genres': []
        }
        try:
            apev2 = APEv2(self.file_path)
            keys = apev2.keys()
            meta['title'] = str(apev2['Title']) if 'Title' in keys else None
            meta['artists'] = parse_multiple_value(str(apev2['Artist'])) if 'Artist' in keys else []
            meta['album'] = str(apev2['Album']) if 'Album' in keys else None
            meta['year'] = parse_year(str(apev2['Year'])) if 'Year' in keys else None
            meta['genres'] = parse_multiple_value(str(apev2['Genre'])) if 'Genre' in keys else []
            return meta
        except APENoHeaderError:
            return None
    
    def to_dict(self):
        return {
            'path': self.file_path,
            'encoding': self.meta_encoding,
            'version': self.meta_version,
            'meta': {**self.meta_data['primary'], **self.meta_data['additional']},
        }
    
    def to_fileinfo(self) -> FileInfo:
        meta_data = self.meta_data
        return FileInfo(
            path=self.file_path, 
            encoding=self.meta_encoding, 
            version=self.meta_version,
            meta_id3=meta_data['primary'],
            meta_apev2=self.apev2_data,
            meta_additional=meta_data['additional']
        )
    
    def update_version(self, use_apev2=False, del_id3v1=True, del_apev2=False):
        '''handle meta data
        if the version is ID3v1, fix the encoding and upgrade to ID3v2.4
        if APEv2 exists, use APEv2 data to replace ID3 tags (only replace title, artist, album, year, genre fields)
        del_id3v1: whether to delete ID3v1 tag
        del_apev2: whether to delete APEv2 tag
        '''
        id3_tag = ID3(self.file_path)
        for key in id3_tag:
            if hasattr(id3_tag[key], 'text'):
                if hasattr(id3_tag[key], 'encoding'):
                    if isinstance(id3_tag[key].text, list):
                        id3_tag[key].text = [decode_tag_value(text, id3_tag[key].encoding) for text in id3_tag[key].text]
                        id3_tag[key].encoding = Encoding.UTF8
                    else:
                        id3_tag[key].text = decode_tag_value(id3_tag[key].text, id3_tag[key].encoding)
                        id3_tag[key].encoding = Encoding.UTF8

        if use_apev2:
            try:
                for key in _APEv2_KEY_MAP:
                    apev2 = APEv2(self.file_path)
                    if key in apev2.keys() and _APEv2_KEY_MAP[key] in id3_tag:
                        if isinstance(apev2[key], list):
                            new_text = []
                            for item in apev2[key]:
                                new_text.append(item.strip() if isinstance(item, str) else item)
                            id3_tag[_APEv2_KEY_MAP[key]].text = [*new_text]
                        elif isinstance(apev2[key], str):
                            id3_tag[_APEv2_KEY_MAP[key]].text = parse_multiple_value(apev2[key])
            except:
                pass

        id3_tag.save(str(self.file_path), v1=0 if del_id3v1 else 1, v2_version=4)

        if del_apev2:  # 删除APEv2标签
            try:
                apev2_tag = APEv2(self.file_path)
                apev2_tag.delete()
                apev2_tag.save()
            except:
                pass

        self.init_version()
        
    def update_meta_version(self, use_apev2=False, del_id3v1=True, del_apev2=False) -> None:
        '''
        [Deprecated]
        handle meta data
        if the version is ID3v1, fix the encoding and upgrade to ID3v2.4
        if APEv2 exists, use APEv2 data to replace ID3 tags (only replace title, artist, album, year, genre fields)
        del_id3v1: whether to delete ID3v1 tag
        del_apev2: whether to delete APEv2 tag
        '''
        tag = MutagenFile(self.file_path, easy=True)
        tag_decoded = decode_object(dict(tag.tags), self.meta_encoding)
        for k, v in tag_decoded.items():
            tag[k] = v
        if use_apev2:
            keys = tag_decoded.keys()
            for k, v in self.apev2_data.items():
                if k == 'artists' and v != []:
                    tag['artist'] = v
                elif k == 'genres' and v != []:
                    tag['genre'] = v
                elif k in keys and v is not None:
                    tag[k] = v

        tag.save(self.file_path, v1=0 if del_id3v1 else 1)
        if del_apev2:
            try:
                tag = APEv2(self.file_path)
                tag.delete()
                tag.save()
            except:
                pass
        self.init_version()

    def update_metadata(self, meta: dict, del_id3v1=True, del_apev2=False) -> None:
        write_metadata(self.file_path, meta)
        if del_id3v1:
            tag = MutagenFile(self.file_path, easy=True)
            tag.save(self.file_path, v1=0)
        if del_apev2:
            try:
                tag = APEv2(self.file_path)
                tag.delete()
                tag.save()
            except:
                pass
        self.init_version()

    def update_meta_data(self, meta: dict, del_id3v1=True, del_apev2=False) -> None:
        '''
        [Deprecated]
        update metadata
        '''
        tag = MutagenFile(self.file_path, easy=True)
        for key in meta.keys():
            if key == 'year':
                tag['date'] = str(meta[key])
            elif key in _KEY_MAP.keys(): 
                tag[_KEY_MAP[key]] = meta[key]
            else:
                tag[key] = meta[key]

        tag.save(self.file_path, v1=0 if del_id3v1 else 1)
        if del_apev2:
            try:
                tag = APEv2(self.file_path)
                tag.delete()
                tag.save()
            except:
                pass
        self.init_version()