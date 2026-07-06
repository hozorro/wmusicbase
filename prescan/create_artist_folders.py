# -*- encoding: utf-8 -*-
'''
@File      :   create_artist_folders.py
@Desc      :   Create folders for artists that don't have corresponding folders.
               Run this script after scanning to create missing artist folders.

Usage:
    python -m prescan.create_artist_folders
    python -m prescan.create_artist_folders --library /path/to/library
    python -m prescan.create_artist_folders --db inspect_result.db
    python -m prescan.create_artist_folders --dry-run  # preview only, don't create
'''


import re
import typer
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from prescan.models import InspectBase, InsArtist
from prescan.database import create_inspect_engine
from app.utils.pinyin import get_artist_sort_fields


# ANSI color codes
_COLORS = {
    'green': '\033[92m',
    'yellow': '\033[93m',
    'blue': '\033[94m',
    'dim': '\033[2m',
    'reset': '\033[0m',
    'bold': '\033[1m',
}


def _c(text: str, color: str) -> str:
    '''wrap text with ANSI color'''
    return f'{_COLORS.get(color, "")}{text}{_COLORS["reset"]}'


# Windows invalid folder name characters: < > : " / \ | ? *
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


def get_initial_group(initial: str) -> str:
    '''compute initial group name from pinyin initial'''
    if initial == '_':
        return 'Z_'
    elif 'A' <= initial <= 'G':
        return 'A-G'
    elif 'H' <= initial <= 'N':
        return 'H-N'
    elif 'O' <= initial <= 'T':
        return 'O-T'
    else:
        return 'U-Z'


def is_chinese_name(name: str) -> bool:
    '''check if the name is primarily Chinese'''
    if not name:
        return False
    # check if first character is Chinese
    first_char = name[0]
    # Chinese Unicode range: \u4e00-\u9fff
    return '\u4e00' <= first_char <= '\u9fff'


def create_artist_folders(library_path: Path, db_path: Path, dry_run: bool = False) -> None:
    '''create folders for artists without corresponding folders'''

    if not library_path.exists():
        print(_c(f'Error: Library path does not exist: {library_path}', 'yellow'))
        return

    # connect to database
    engine = create_inspect_engine(db_path)

    with Session(engine) as session:
        # get all artists with empty dir_path
        artists = session.execute(
            select(InsArtist).where(
                (InsArtist.dir_path == '') | InsArtist.dir_path.is_(None)
            )
        ).scalars().all()

        if not artists:
            print(_c('No artists need folder creation.', 'green'))
            return

        print(_c(f'Found {len(artists)} artists without folders', 'bold'))
        print()

        created_count = 0
        skipped_count = 0
        error_count = 0

        for artist in artists:
            # sanitize folder name
            safe_name = sanitize_folder_name(artist.name)

            # determine area
            area = 'Chinese' if is_chinese_name(artist.name) else 'Foreign'

            # determine char_range
            _, initial = get_artist_sort_fields(artist.name)
            group = get_initial_group(initial)

            # build target path
            target_dir = library_path / area / group / safe_name

            # check if already exists
            if target_dir.exists():
                print(f'  {_c("SKIP", "dim")} {artist.name:30s} -> folder already exists: {target_dir.relative_to(library_path)}')
                skipped_count += 1
                continue

            if dry_run:
                print(f'  {_c("DRY-RUN", "blue")} {artist.name:30s} -> would create: {target_dir.relative_to(library_path)}')
                created_count += 1
                continue

            # create folder
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                print(f'  {_c("CREATED", "green")} {artist.name:30s} -> {target_dir.relative_to(library_path)}')
                created_count += 1

                # update database
                rel_path = str(target_dir.relative_to(library_path)).replace('\\', '/')
                artist.dir_path = rel_path

            except Exception as e:
                print(f'  {_c("ERROR", "yellow")} {artist.name:30s} -> {e}')
                error_count += 1

        # commit changes
        if not dry_run:
            session.commit()

        print()
        print(_c('═' * 60, 'bold'))
        if dry_run:
            print(f'  Dry-run complete: {created_count} folders would be created')
        else:
            print(f'  Complete: {created_count} created, {skipped_count} skipped, {error_count} errors')
        print(_c('═' * 60, 'bold'))


app = typer.Typer(help='Create folders for artists without corresponding folders')


@app.command()
def run(
    library: Path = typer.Option(None, '--library', '-l', help='音乐库目录路径'),
    db: Path = typer.Option(Path('inspect_result.db'), '--db', '-d', help='检查结果数据库路径'),
    dry_run: bool = typer.Option(False, '--dry-run', '-n', help='预览模式，不实际创建文件夹'),
):
    '''为没有对应文件夹的歌手创建文件夹'''

    # resolve library path
    if library:
        library_path = library.resolve()
    else:
        try:
            from app.core.config import settings
            library_path = settings.MUSIC_LIBRARY_PATH.resolve()
        except Exception:
            typer.echo('Error: Could not determine music library path.', err=True)
            typer.echo('Please specify --library or configure MUSIC_LIBRARY_PATH in .env', err=True)
            raise typer.Exit(code=1)

    if not library_path.exists():
        typer.echo(f'Error: Library path does not exist: {library_path}', err=True)
        raise typer.Exit(code=1)

    if not db.exists():
        typer.echo(f'Error: Database not found: {db}', err=True)
        typer.echo('Run "scan" command first.', err=True)
        raise typer.Exit(code=1)

    print(f'Library: {library_path}')
    print(f'Database: {db}')
    print()

    create_artist_folders(library_path, db, dry_run)


if __name__ == '__main__':
    app()
