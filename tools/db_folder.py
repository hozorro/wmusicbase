import shutil
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.core.db import get_db
from app.models import Folder, Track
from app.schemas.folder import FolderResponse

async def get_folder(folder_id: int) -> Folder | None:
    async for db in get_db():
        stmt = (
            select(Folder)
            .where(Folder.id == folder_id)
            .options(
                selectinload(Folder.children).load_only(Folder.id, Folder.path),
                selectinload(Folder.tracks).load_only(Track.id, Track.title, Track.cover_art_hash),
            )   
        )
        result = await db.execute(stmt)
        folder = result.scalar_one_or_none()
        if folder:
            print(
                FolderResponse
                .model_validate(folder)
                .model_dump_json(indent=4, ensure_ascii=False)
            )

root_path = r'D:\tmp\artist_covers\have_dir'
set_path = r'H:\musiclibcorrect'
def get_folder_artist_arts(area: str, char_range: str):
    iter_root = Path(root_path) / area / char_range
    results = []
    for dir in iter_root.iterdir():
        artist_name = dir.name
        artist_covers = []
        for face in dir.glob('*.jpg'):
            artist_covers.append(face.stem)
        results.append({'name': artist_name, 'covers': artist_covers})
    return results

def get_folder_artist_art_file(area: str, char_range: str, artist_name: str, file_stem: str):
    return Path(root_path) / area / char_range / artist_name / f'{file_stem}.jpg'

def set_folder_artist_art(area: str, char_range: str, covers: list[dict[str, str]]):
    exists = []
    no_dirs = []
    created = []
    for cover in covers:
        artist_name = cover['name']
        file_stem = cover['cover']
        src_path = Path(root_path) / area / char_range / artist_name / f'{file_stem}.jpg'
        dst_path = Path(set_path) / area / char_range / artist_name / 'face.jpg'
        
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

def find_has_cover_artists():
    root_folder = Path(r'H:\musiclibcorrect')
    have_cover_artists = []
    areas = ['Chinese', 'Foreign']
    char_ranges = ['A-G', 'H-N', 'O-T', 'U-Z', 'Z_']
    for area in areas:
        for char_range in char_ranges:
            for artist_dir in (root_folder / area / char_range).iterdir():
                covers = artist_dir.glob('*.jpg')
                if len(list(covers)) > 0:
                    have_cover_artists.append(artist_dir.name)
    return have_cover_artists

if __name__ == '__main__':
    # import asyncio
    # asyncio.run(get_folder(33))
    print(find_has_cover_artists())
