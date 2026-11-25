# -*- encoding: utf-8 -*-
'''
@Desc  : centralized audio format knowledge: MP4 atoms, MIME and upload policy

Kept free of `settings` and `metadata` imports so it can be used by prescan,
the API layer and the metadata module without circular imports.
'''

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from mutagen.mp4 import MP4, MP4Cover  # pyright: ignore[reportPrivateImportUsage]


MP4_SUFFIXES: frozenset[str] = frozenset({'.m4a'})

AUDIO_MIME_BY_SUFFIX: dict[str, str] = {
    '.mp3': 'audio/mpeg',
    '.flac': 'audio/flac',
    '.m4a': 'audio/mp4',
    '.mp4': 'audio/mp4',
}

ALLOWED_UPLOAD_CONTENT_TYPES: frozenset[str] = frozenset({
    'audio/mpeg',
    'audio/flac',
    'audio/mp4',
    'audio/x-m4a',
    'audio/mp4a-latm',
    'audio/aac',
    'application/octet-stream',
})

MP4_ATOM_MAP: dict[str, str] = {
    'title': '©nam',
    'artists': '©ART',
    'album': '©alb',
    'albumartist': 'aART',
    'year': '©day',
    'genres': '©gen',
}

MP4_FREEFORM_MAP: dict[str, str] = {
    'mb_artistids': 'MusicBrainz Artist Id',
    'mb_albumartistid': 'MusicBrainz Album Artist Id',
    'mb_albumid': 'MusicBrainz Album Id',
    'mb_trackid': 'MusicBrainz Track Id',
    'acoustid_id': 'Acoustid Id',
}

_FREEFORM_PREFIX = '----:com.apple.iTunes:'
_LIST_FIELDS = frozenset({'artists', 'albumartist', 'genres',
                          'mb_artistids', 'mb_albumartistid'})


def _freeform_key(atom_name: str) -> str:
    return _FREEFORM_PREFIX + atom_name


def audio_file_type(path: str | Path) -> str:
    '''Return the logical file type used by AudioMeta / FileInfo.'''
    suffix = Path(path).suffix.lower()
    if suffix == '.mp3':
        return 'mp3'
    if suffix == '.flac':
        return 'flac'
    if suffix in MP4_SUFFIXES:
        return 'm4a'
    return 'NA'


def audio_mime_for(path: str | Path) -> str | None:
    '''Explicit suffix -> MIME mapping; None lets the caller fall back.'''
    return AUDIO_MIME_BY_SUFFIX.get(Path(path).suffix.lower())


def is_allowed_upload(
    filename: str | None,
    content_type: str | None,
    allowed_extensions: Iterable[str],
) -> bool:
    '''Both the suffix and the Content-Type must be allowed.'''
    if not filename or not content_type:
        return False
    suffix = Path(filename).suffix.lower()
    if suffix not in {e.lower() for e in allowed_extensions}:
        return False
    normalized = content_type.split(';', 1)[0].strip().lower()
    return normalized in ALLOWED_UPLOAD_CONTENT_TYPES


def _mp4_cover_format(data: bytes) -> int:
    '''MP4Cover needs an imageformat int, not a MIME string.'''
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return MP4Cover.FORMAT_PNG
    return MP4Cover.FORMAT_JPEG


def mp4_cover_bytes(audio: Any) -> bytes | None:
    '''Read the first `covr` atom by capability, not by file suffix.'''
    tags = getattr(audio, 'tags', None)
    if tags is None or not hasattr(tags, 'get'):
        return None
    try:
        covers = tags.get('covr')
    except Exception:
        return None
    if not covers or isinstance(covers, (str, bytes, bytearray)):
        return None
    try:
        first = covers[0]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(first, (bytes, bytearray, memoryview)):
        return None
    return bytes(first)


def read_mp4_freeform(file_path: str | Path) -> dict[str, Any]:
    '''Read iTunes `----` atoms that EasyMP4 does not expose (notably AcoustID).'''
    out: dict[str, Any] = {}
    try:
        audio = MP4(file_path)
    except Exception:
        return out
    tags = audio.tags
    if not tags:
        return out
    for target_field, atom_name in MP4_FREEFORM_MAP.items():
        raw = tags.get(_freeform_key(atom_name))
        if not raw:
            continue
        items = raw if isinstance(raw, (list, tuple)) else [raw]
        values = [
            item.decode('utf-8', errors='ignore') if isinstance(item, bytes) else str(item)
            for item in items
        ]
        values = [v for v in values if v]
        if not values:
            continue
        out[target_field] = values if target_field in _LIST_FIELDS else values[0]
    return out


def write_mp4_metadata(file_path: str | Path, meta: dict[str, Any]) -> None:
    '''Write canonical metadata into MP4/iTunes atoms; trkn/disk are untouched.'''
    audio = MP4(file_path)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    if tags is None:
        raise ValueError(f'Cannot create MP4 tags for {file_path}')

    for field, atom in MP4_ATOM_MAP.items():
        value = meta.get(field)
        if not value:
            continue
        items = value if isinstance(value, (list, tuple)) else [value]
        tags[atom] = [str(v) for v in items if v]

    for field, atom_name in MP4_FREEFORM_MAP.items():
        value = meta.get(field)
        if not value:
            continue
        items = value if isinstance(value, (list, tuple)) else [value]
        encoded = [str(v).encode('utf-8') for v in items if v]
        if encoded:
            tags[_freeform_key(atom_name)] = encoded

    cover = meta.get('cover_art_data')
    if isinstance(cover, bytes) and cover:
        tags['covr'] = [MP4Cover(cover, imageformat=_mp4_cover_format(cover))]

    audio.save()
