# -*- encoding: utf-8 -*-
'''
@File      :   scanner.py
@Desc      :   Music library scanner for inspection - walks directory, parses metadata, stores to SQLite
'''


import sys
from pathlib import Path
from sqlalchemy.orm import Session

from sqlalchemy import select as sa_select

from prescan.database import create_inspect_engine
from prescan.models import (
    InspectBase, InsArtist, InsAlbum, InsGenre, InsTrack, InsIssue,
)
from prescan.checks import get_all_checks
from prescan.checks.base import Issue

from app.utils.metadata import parse_metadata, easy_metadata, extract_cover_art_hash
from app.utils.pinyin import get_artist_sort_fields

COMMIT_BATCH_SIZE = 200


class InspectScanner:
    '''scan music library and run inspection checks'''

    def __init__(self, library_path: Path, db_path: Path, extensions: list[str] | None = None):
        self.library_path = library_path.resolve()
        self.db_path = db_path
        self.extensions = extensions or ['.mp3', '.flac']

        # in-memory caches
        self._artist_cache: dict[str, InsArtist] = {}
        self._album_cache: dict[tuple[str, int | None], InsAlbum] = {}
        self._genre_cache: dict[str, InsGenre] = {}
        # artist folder map: {folder_name: relative_path}, built before scanning
        self._artist_dir_map: dict[str, str] = {}

        # counters
        self._total_files = 0
        self._processed = 0
        self._errors = 0

    def run(self) -> list[Issue]:
        '''main entry: scan library, then run all checks'''
        print(f'📂 Library: {self.library_path}')
        print(f'💾 Database: {self.db_path}')
        print()

        # 1. setup database
        engine = create_inspect_engine(self.db_path)
        InspectBase.metadata.create_all(engine)

        # 2. build artist directory map (scan directory structure)
        self._build_artist_dir_map()
        print(f'📁 Found {len(self._artist_dir_map)} artist folders in library')

        # 3. collect all music files
        music_files = self._collect_files()
        self._total_files = len(music_files)
        print(f'🔍 Found {self._total_files} music files')
        print()

        # 4. scan files
        with Session(engine) as session:
            self._scan_files(session, music_files)
            session.commit()
            print()
            print(f'✅ Scan complete: {self._processed} processed, {self._errors} errors')
            print()

            # 5. run all checks
            all_issues = self._run_checks(session)
            session.commit()

        print()
        print(f'🏁 Inspection complete: {len(all_issues)} issues found')
        return all_issues

    def _build_artist_dir_map(self):
        '''
        scan the library directory structure to build a map of artist folders.
        directory structure: area/char_range/artist_name/...
        result: {artist_folder_name: relative_path}
        '''
        if not self.library_path.exists():
            return
        for area_dir in self.library_path.iterdir():
            if not area_dir.is_dir():
                continue
            for range_dir in area_dir.iterdir():
                if not range_dir.is_dir():
                    continue
                for artist_dir in range_dir.iterdir():
                    if artist_dir.is_dir():
                        name = artist_dir.name
                        rel_path = str(artist_dir.relative_to(self.library_path)).replace('\\', '/')
                        self._artist_dir_map[name] = rel_path

    def _collect_files(self) -> list[Path]:
        '''collect all music files from the library directory'''
        files = []
        for ext in self.extensions:
            files.extend(self.library_path.rglob(f'*{ext}'))
        # also try uppercase extensions
        for ext in self.extensions:
            files.extend(self.library_path.rglob(f'*{ext.upper()}'))
        # deduplicate (in case of case-insensitive filesystem)
        seen = set()
        unique = []
        for f in files:
            key = str(f.resolve()).lower()
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return sorted(unique)

    def _scan_files(self, session: Session, files: list[Path]) -> None:
        '''parse metadata and store to SQLite'''
        for i, file_path in enumerate(files):
            self._process_file(session, file_path)
            # progress
            progress = (i + 1) / self._total_files * 100
            sys.stdout.write(f'\r  [{i + 1}/{self._total_files}] ({progress:.1f}%) {file_path.name[:50]}')
            sys.stdout.flush()
            # batch commit
            if (i + 1) % COMMIT_BATCH_SIZE == 0:
                session.commit()

    def _process_file(self, session: Session, file_path: Path) -> None:
        '''process a single music file'''
        rel_path = file_path.relative_to(self.library_path)
        rel_str = str(rel_path).replace('\\', '/')
        parts = rel_path.parts

        # extract directory structure info
        dir_level = len(parts)
        dir_area = parts[0] if len(parts) >= 1 else None
        dir_char_range = parts[1] if len(parts) >= 2 else None

        # parse metadata
        meta = None
        cover_hash = None
        error_msg = None
        try:
            if file_path.suffix.lower() == '.mp3':
                meta = parse_metadata(file_path)
            else:
                meta = easy_metadata(file_path)
            cover_hash = extract_cover_art_hash(file_path)
        except Exception as e:
            error_msg = str(e)

        if meta is None and error_msg is None:
            error_msg = 'Failed to parse metadata (returned None)'

        # create/get entities
        artist_name = 'Unknown Artist'
        album_title = ''
        artists: list[InsArtist] = []
        genres: list[InsGenre] = []
        album: InsAlbum | None = None
        track_title = file_path.stem
        duration = 0.0
        bitrate = 0
        bitrate_mode = None
        year = None

        if meta:
            track_title = meta.get('title', '') or file_path.stem
            duration = meta.get('duration', 0.0) or 0.0
            bitrate = meta.get('bitrate', 0) or 0
            bitrate_mode = meta.get('bitrate_mode', '')
            year = meta.get('year', 0) or None

            # infer album artist for album dedup
            albumartist_list = meta.get('albumartist', [])
            artist_list = meta.get('artists', [])
            if albumartist_list:
                album_artist_name = albumartist_list[0]
            elif artist_list:
                album_artist_name = artist_list[0]
            else:
                album_artist_name = 'Unknown Artist'

            # get/create artists
            for a_name in artist_list:
                a_name = a_name.strip() if a_name else ''
                if a_name:
                    artist = self._get_or_create_artist(session, a_name, file_path)
                    if artist and artist not in artists:
                        artists.append(artist)

            # get/create album
            album_title = meta.get('album', '') or ''
            if album_title:
                album_artist = self._artist_cache.get(album_artist_name.strip())
                album = self._get_or_create_album(session, album_title, album_artist, file_path, year)

            # get/create genres
            for g_name in meta.get('genres', []):
                g_name = g_name.strip() if g_name else ''
                if g_name:
                    genre = self._get_or_create_genre(session, g_name)
                    if genre and genre not in genres:
                        genres.append(genre)

        # create track
        track = InsTrack(
            file_path=rel_str,
            file_name=file_path.name,
            title=track_title,
            duration=duration,
            bitrate=bitrate,
            bitrate_mode=bitrate_mode or None,
            year=year,
            has_cover_art=cover_hash is not None,
            cover_art_hash=cover_hash,
            album_id=album.id if album else None,
            dir_level=dir_level,
            dir_area=dir_area,
            dir_char_range=dir_char_range,
            parse_error=error_msg is not None,
            error_message=error_msg,
        )
        track.artists = artists
        track.genres = genres
        session.add(track)

        if error_msg:
            self._errors += 1
        else:
            self._processed += 1

    def _get_or_create_artist(self, session: Session, name: str, file_path: Path) -> InsArtist | None:
        '''get or create an artist, with face.jpg check'''
        name = name.strip()
        if not name:
            return None

        if name in self._artist_cache:
            return self._artist_cache[name]

        # check DB
        existing = session.execute(
            sa_select(InsArtist).where(InsArtist.name == name)
        ).scalar_one_or_none()
        if existing:
            self._artist_cache[name] = existing
            return existing

        # determine artist dir path: check current dir first, then fallback to library-wide search
        rel = file_path.relative_to(self.library_path)
        parts = rel.parts
        artist_dir = ''
        has_face = False
        if len(parts) >= 3:
            dir_name = parts[2]  # area/char_range/artist_name/...
            if dir_name == name:
                # current file is in this artist's own folder
                artist_dir = '/'.join(parts[:3])
            else:
                # featured artist: look up in the pre-built directory map
                artist_dir = self._artist_dir_map.get(name, '')

            if artist_dir:
                artist_abs = self.library_path / artist_dir
                if artist_abs.exists():
                    has_face = (artist_abs / 'face.jpg').exists()

        sort_name, pinyin_initial = get_artist_sort_fields(name)

        artist = InsArtist(
            name=name,
            dir_path=artist_dir,
            has_face_jpg=has_face,
            sort_name=sort_name,
            pinyin_initial=pinyin_initial,
        )
        session.add(artist)
        session.flush()  # get the ID
        self._artist_cache[name] = artist
        return artist

    def _get_or_create_album(self, session: Session, title: str, artist: InsArtist | None,
                              file_path: Path, year: int | None) -> InsAlbum | None:
        '''get or create an album'''
        title = title.strip()
        if not title:
            return None

        artist_id = artist.id if artist else None
        cache_key = (title, artist_id)

        if cache_key in self._album_cache:
            return self._album_cache[cache_key]

        # check DB
        existing = session.execute(
            sa_select(InsAlbum).where(
                InsAlbum.title == title,
                InsAlbum.artist_id == artist_id,
            )
        ).scalar_one_or_none()
        if existing:
            self._album_cache[cache_key] = existing
            return existing

        # determine album dir path
        rel = file_path.relative_to(self.library_path)
        parts = rel.parts
        album_dir = '/'.join(parts[:4]) if len(parts) >= 4 else ''

        album = InsAlbum(
            title=title,
            year=year,
            dir_path=album_dir,
            artist_id=artist_id,
        )
        session.add(album)
        session.flush()
        self._album_cache[cache_key] = album
        return album

    def _get_or_create_genre(self, session: Session, name: str) -> InsGenre | None:
        '''get or create a genre'''
        name = name.strip()
        if not name:
            return None

        if name in self._genre_cache:
            return self._genre_cache[name]

        # check DB
        existing = session.execute(
            sa_select(InsGenre).where(InsGenre.name == name)
        ).scalar_one_or_none()
        if existing:
            self._genre_cache[name] = existing
            return existing

        genre = InsGenre(name=name)
        session.add(genre)
        session.flush()
        self._genre_cache[name] = genre
        return genre

    def _run_checks(self, session: Session) -> list[Issue]:
        '''run all registered checks and store issues'''
        all_issues: list[Issue] = []
        checks = get_all_checks()
        print(f'🔬 Running {len(checks)} checks...')

        for check_cls in checks:
            check = check_cls(session, self.library_path)
            print(f'  ├─ {check.description}...', end=' ')
            try:
                issues = check.run()
                for issue in issues:
                    session.add(InsIssue(**issue.to_dict()))
                all_issues.extend(issues)
                print(f'{len(issues)} issues')
            except Exception as e:
                print(f'ERROR: {e}')

        return all_issues
