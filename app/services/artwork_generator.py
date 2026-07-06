# -*- encoding: utf-8 -*-
'''
@File      :   artwork_generator.py
@Time      :   2026/06/23 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   Background artwork generation service with progress tracking
'''


from sqlalchemy import select
from app.models import Artist, Album, Track, Playlist
from app.services.artwork_service import ArtworkService
from app.core.state import system_state
from app.core.logger import logger


class ArtworkGenerator:
    '''Generate all artwork files with progress tracking and cancellation support'''

    def __init__(self, service: ArtworkService, art_types: list[str] | None = None):
        '''
        Args:
            service: ArtworkService instance with db session
            art_types: list of art types to generate, e.g. ['artist', 'album', 'track', 'playlist']
                       None means all types
        '''
        self.service = service
        self.art_types = art_types or ['artist', 'album', 'track', 'playlist']

    async def run(self):
        '''Run the artwork generation process'''
        system_state.init_artwork_gen_state()
        try:
            for art_type in self.art_types:
                if system_state.is_artwork_gen_canceled:
                    logger.info('Artwork generation canceled by user')
                    break

                if art_type == 'artist':
                    await self._generate_artist_artworks()
                elif art_type == 'album':
                    await self._generate_album_artworks()
                elif art_type == 'track':
                    await self._generate_track_artworks()
                elif art_type == 'playlist':
                    await self._generate_playlist_artworks()

            # mark as done
            if system_state.artwork_progress:
                system_state.artwork_progress['phase'] = 'done'
                system_state.artwork_progress['current_item'] = ''
            logger.info('Artwork generation completed')
        except Exception as e:
            logger.error(f'Artwork generation failed: {e}')
        finally:
            system_state.reset_artwork_gen_state()

    async def _generate_artist_artworks(self):
        '''Generate artist face and portrait artworks'''
        result = await self.service.db.execute(select(Artist))
        artists = result.scalars().all()

        # phase: artist_face
        await self._run_phase(
            phase_name='artist_face',
            items=artists,
            get_cache_path=lambda a: self.service.settings.ARTIST_ARTWORK_DIR / f'{a.id}_face.jpg',
            generate_fn=lambda a: self.service.get_or_cache_artist_artwork(a.id, 'face'),
            item_label=lambda a: f'{a.id}:{a.name}',
        )

        if system_state.is_artwork_gen_canceled:
            return

        # phase: artist_portrait
        await self._run_phase(
            phase_name='artist_portrait',
            items=artists,
            get_cache_path=lambda a: self.service.settings.ARTIST_ARTWORK_DIR / f'{a.id}_portrait.jpg',
            generate_fn=lambda a: self.service.get_or_cache_artist_artwork(a.id, 'portrait'),
            item_label=lambda a: f'{a.id}:{a.name}',
        )

    async def _generate_album_artworks(self):
        '''Generate album artworks'''
        result = await self.service.db.execute(select(Album))
        albums = result.scalars().all()

        await self._run_phase(
            phase_name='album',
            items=albums,
            get_cache_path=lambda a: self.service.settings.ALBUM_ARTWORK_DIR / f'{a.id}.jpg',
            generate_fn=lambda a: self.service.get_or_cache_album_artwork(a.id),
            item_label=lambda a: f'{a.id}:{a.title}',
        )

    async def _generate_track_artworks(self):
        '''Generate track artworks'''
        result = await self.service.db.execute(select(Track).where(Track.is_deleted == False))
        tracks = result.scalars().all()

        await self._run_phase(
            phase_name='track',
            items=tracks,
            get_cache_path=lambda t: self.service.settings.TRACK_ARTWORK_DIR / f'{t.id}.jpg',
            generate_fn=lambda t: self.service.get_or_cache_track_artwork(t.id),
            item_label=lambda t: f'{t.id}:{t.title or t.file_name}',
        )

    async def _generate_playlist_artworks(self):
        '''Generate playlist artworks'''
        result = await self.service.db.execute(select(Playlist))
        playlists = result.scalars().all()

        await self._run_phase(
            phase_name='playlist',
            items=playlists,
            get_cache_path=lambda p: self.service.settings.PLAYLIST_ARTWORK_DIR / f'{p.id}.jpg',
            generate_fn=lambda p: self.service.get_or_cache_playlist_artwork(p.id),
            item_label=lambda p: f'{p.id}:{p.name}',
        )

    async def _run_phase(
        self,
        phase_name: str,
        items: list,
        get_cache_path,
        generate_fn,
        item_label,
    ):
        '''
        Run a single generation phase
        Args:
            phase_name: name of the phase (e.g. 'artist_face')
            items: list of entities to process
            get_cache_path: function to get cache file path for an entity
            generate_fn: async function to generate artwork for an entity
            item_label: function to get a display label for an entity
        '''
        progress = system_state.artwork_progress
        progress['phase'] = phase_name
        progress['phase_total'] = len(items)
        progress['phase_processed'] = 0
        progress['phase_generated'] = 0
        progress['phase_skipped'] = 0
        progress['phase_failed'] = 0

        logger.info(f'Artwork generation phase [{phase_name}]: {len(items)} items')

        for item in items:
            if system_state.is_artwork_gen_canceled:
                break

            progress['current_item'] = item_label(item)
            cache_path = get_cache_path(item)

            if cache_path.exists():
                progress['phase_skipped'] += 1
                progress['total_skipped'] += 1
            else:
                try:
                    result = await generate_fn(item)
                    if result:
                        progress['phase_generated'] += 1
                        progress['total_generated'] += 1
                    else:
                        progress['phase_failed'] += 1
                        progress['total_failed'] += 1
                except Exception as e:
                    logger.warning(f'Failed to generate {phase_name} artwork for {item_label(item)}: {e}')
                    progress['phase_failed'] += 1
                    progress['total_failed'] += 1

            progress['phase_processed'] += 1
