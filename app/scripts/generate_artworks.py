# -*- encoding: utf-8 -*-
'''
@File      :   generate_artworks.py
@Time      :   2026/03/06 10:30:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   Pre-generate all artwork static files for nginx serving

Usage:
    python -m app.scripts.generate_artworks
    python -m app.scripts.generate_artworks --dry-run  # preview only
    python -m app.scripts.generate_artworks --type artist  # only artists
    python -m app.scripts.generate_artworks --type album   # only albums
    python -m app.scripts.generate_artworks --type track   # only tracks
'''


import asyncio
import typer
from pathlib import Path
from sqlalchemy import select
from app.core.config import settings
from app.core.db import async_session
from app.models import Artist, Album, Track, Playlist
from app.services.artwork_service import ArtworkService

app = typer.Typer(help='Pre-generate all artwork static files')


class ArtworkGenerator:
    '''Generate all artwork files'''
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.stats = {
            'artist_face': {'total': 0, 'generated': 0, 'skipped': 0, 'failed': 0},
            'artist_portrait': {'total': 0, 'generated': 0, 'skipped': 0, 'failed': 0},
            'album': {'total': 0, 'generated': 0, 'skipped': 0, 'failed': 0},
            'track': {'total': 0, 'generated': 0, 'skipped': 0, 'failed': 0},
            'playlist': {'total': 0, 'generated': 0, 'skipped': 0, 'failed': 0},
        }
    
    async def generate_artist_artworks(self, service: ArtworkService):
        '''Generate all artist artworks (face and portrait)'''
        result = await service.db.execute(select(Artist))
        artists = result.scalars().all()
        
        self.stats['artist_face']['total'] = len(artists)
        self.stats['artist_portrait']['total'] = len(artists)
        
        print(f'\n📸 Generating artist artworks ({len(artists)} artists)...')
        
        for i, artist in enumerate(artists, 1):
            # Generate face artwork
            cache_path = settings.ARTIST_ARTWORK_DIR / f'{artist.id}_face.jpg'
            if cache_path.exists():
                self.stats['artist_face']['skipped'] += 1
            else:
                try:
                    if not self.dry_run:
                        result = await service.get_or_cache_artist_artwork(artist.id, 'face')
                        if result:
                            self.stats['artist_face']['generated'] += 1
                        else:
                            self.stats['artist_face']['failed'] += 1
                    else:
                        self.stats['artist_face']['generated'] += 1
                except Exception as e:
                    print(f'  ❌ Failed to generate face for artist {artist.id} ({artist.name}): {e}')
                    self.stats['artist_face']['failed'] += 1
            
            # Generate portrait artwork
            cache_path = settings.ARTIST_ARTWORK_DIR / f'{artist.id}_portrait.jpg'
            if cache_path.exists():
                self.stats['artist_portrait']['skipped'] += 1
            else:
                try:
                    if not self.dry_run:
                        result = await service.get_or_cache_artist_artwork(artist.id, 'portrait')
                        if result:
                            self.stats['artist_portrait']['generated'] += 1
                        else:
                            self.stats['artist_portrait']['failed'] += 1
                    else:
                        self.stats['artist_portrait']['generated'] += 1
                except Exception as e:
                    print(f'  ❌ Failed to generate portrait for artist {artist.id} ({artist.name}): {e}')
                    self.stats['artist_portrait']['failed'] += 1
            
            if i % 50 == 0:
                print(f'  Progress: {i}/{len(artists)}')
    
    async def generate_album_artworks(self, service: ArtworkService):
        '''Generate all album artworks'''
        result = await service.db.execute(select(Album))
        albums = result.scalars().all()
        
        self.stats['album']['total'] = len(albums)
        
        print(f'\n💿 Generating album artworks ({len(albums)} albums)...')
        
        for i, album in enumerate(albums, 1):
            cache_path = settings.ALBUM_ARTWORK_DIR / f'{album.id}.jpg'
            if cache_path.exists():
                self.stats['album']['skipped'] += 1
            else:
                try:
                    if not self.dry_run:
                        result = await service.get_or_cache_album_artwork(album.id)
                        if result:
                            self.stats['album']['generated'] += 1
                        else:
                            self.stats['album']['failed'] += 1
                    else:
                        self.stats['album']['generated'] += 1
                except Exception as e:
                    print(f'  ❌ Failed to generate artwork for album {album.id} ({album.title}): {e}')
                    self.stats['album']['failed'] += 1
            
            if i % 100 == 0:
                print(f'  Progress: {i}/{len(albums)}')
    
    async def generate_track_artworks(self, service: ArtworkService):
        '''Generate all track artworks'''
        result = await service.db.execute(select(Track).where(Track.is_deleted == False))
        tracks = result.scalars().all()
        
        self.stats['track']['total'] = len(tracks)
        
        print(f'\n🎵 Generating track artworks ({len(tracks)} tracks)...')
        
        for i, track in enumerate(tracks, 1):
            cache_path = settings.TRACK_ARTWORK_DIR / f'{track.id}.jpg'
            if cache_path.exists():
                self.stats['track']['skipped'] += 1
            else:
                try:
                    if not self.dry_run:
                        result = await service.get_or_cache_track_artwork(track.id)
                        if result:
                            self.stats['track']['generated'] += 1
                        else:
                            self.stats['track']['failed'] += 1
                    else:
                        self.stats['track']['generated'] += 1
                except Exception as e:
                    print(f'  ❌ Failed to generate artwork for track {track.id} ({track.title}): {e}')
                    self.stats['track']['failed'] += 1
            
            if i % 200 == 0:
                print(f'  Progress: {i}/{len(tracks)}')
    
    async def generate_playlist_artworks(self, service: ArtworkService):
        '''Generate all playlist artworks'''
        result = await service.db.execute(select(Playlist))
        playlists = result.scalars().all()
        
        self.stats['playlist']['total'] = len(playlists)
        
        print(f'\n📋 Generating playlist artworks ({len(playlists)} playlists)...')
        
        for i, playlist in enumerate(playlists, 1):
            cache_path = settings.PLAYLIST_ARTWORK_DIR / f'{playlist.id}.jpg'
            if cache_path.exists():
                self.stats['playlist']['skipped'] += 1
            else:
                try:
                    if not self.dry_run:
                        result = await service.get_or_cache_playlist_artwork(playlist.id)
                        if result:
                            self.stats['playlist']['generated'] += 1
                        else:
                            self.stats['playlist']['failed'] += 1
                    else:
                        self.stats['playlist']['generated'] += 1
                except Exception as e:
                    print(f'  ❌ Failed to generate artwork for playlist {playlist.id} ({playlist.name}): {e}')
                    self.stats['playlist']['failed'] += 1
    
    def print_stats(self):
        '''Print generation statistics'''
        print('\n' + '=' * 60)
        print('📊 Generation Statistics')
        print('=' * 60)
        
        for art_type, stats in self.stats.items():
            total = stats['total']
            generated = stats['generated']
            skipped = stats['skipped']
            failed = stats['failed']
            
            print(f'\n{art_type.upper()}:')
            print(f'  Total:     {total}')
            print(f'  Generated: {generated} ✅')
            print(f'  Skipped:   {skipped} ⏭️  (already cached)')
            print(f'  Failed:    {failed} ❌')
        
        print('\n' + '=' * 60)


async def run_generation(dry_run: bool = False, art_type: str | None = None):
    '''Run the artwork generation'''
    print('=' * 60)
    print('🎨 Artwork Pre-Generation Tool')
    print('=' * 60)
    print(f'Mode: {"DRY RUN (preview only)" if dry_run else "LIVE (will generate files)"}')
    print(f'Artwork directory: {settings.ARTWORK_DIR}')
    
    if dry_run:
        print('\n⚠️  DRY RUN MODE - No files will be created')
    
    generator = ArtworkGenerator(dry_run=dry_run)
    
    async with async_session() as db:
        service = ArtworkService(db, settings)
        
        if art_type is None or art_type == 'artist':
            await generator.generate_artist_artworks(service)
        
        if art_type is None or art_type == 'album':
            await generator.generate_album_artworks(service)
        
        if art_type is None or art_type == 'track':
            await generator.generate_track_artworks(service)
        
        if art_type is None or art_type == 'playlist':
            await generator.generate_playlist_artworks(service)
    
    generator.print_stats()
    
    if dry_run:
        print('\n✅ Dry run completed. No files were created.')
        print('Run without --dry-run to actually generate files.')
    else:
        print('\n✅ Generation completed!')
        print(f'Artwork files are in: {settings.ARTWORK_DIR}')


@app.command()
def generate(
    dry_run: bool = typer.Option(False, '--dry-run', '-n', help='Preview only, do not generate files'),
    art_type: str = typer.Option(None, '--type', '-t', help='Generate only specific type: artist, album, track, playlist'),
):
    '''Pre-generate all artwork static files'''
    if art_type and art_type not in ['artist', 'album', 'track', 'playlist']:
        print(f'❌ Invalid art_type: {art_type}. Must be one of: artist, album, track, playlist')
        raise typer.Exit(1)
    
    asyncio.run(run_generation(dry_run=dry_run, art_type=art_type))


if __name__ == '__main__':
    app()
