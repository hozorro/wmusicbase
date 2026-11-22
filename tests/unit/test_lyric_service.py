# -*- encoding: utf-8 -*-
"""
Tests for app/services/lyric_service.py
Lyric pipeline: search -> score -> lyric -> write `<audio stem>.lrc` next to the audio file.
"""

import json
import time
from types import SimpleNamespace

import pytest

from app.services import lyric_service as lyric_service_module
from app.services.lyric_service import LyricResult, LyricService, score_candidate

LYRIC = (
    '[ti:Test Song]\n'
    '[ar:Test Artist]\n'
    '[00:01.00]first line\n'
    '[00:02.00]second line\n'
    '[00:03.00]third line\n'
)


def _wait_until(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def _fake_http_factory(song_dt_ms: int = 240000):
    def _fake_http(url, timeout):
        if '/cloudsearch' in url:
            return json.dumps({'result': {'songs': [{
                'id': 12345,
                'name': 'Test Song',
                'ar': [{'name': 'Test Artist'}],
                'al': {'name': 'Test Album'},
                'dt': song_dt_ms,
            }]}}), ''
        if '/lyric' in url:
            return json.dumps({'lrc': {'lyric': LYRIC}}), ''
        raise AssertionError(f'unexpected url: {url}')
    return _fake_http


@pytest.fixture
def service(tmp_path):
    settings = SimpleNamespace(
        MUSIC_LIBRARY_PATH=tmp_path,
        LC_NETEASE_API='http://netease.local',
        LC_LRCAPI='http://lrcapi.local',
        LRCLIB_API='https://lrclib.local/api',
    )
    svc = LyricService(settings, http_getter=_fake_http_factory())
    svc.limiter.interval = 0        # no rate limit wait in tests
    svc._fb_limiter.interval = 0
    return svc


@pytest.fixture
def audio_path(tmp_path):
    return tmp_path / 'sub' / 'Test Song.mp3'


def _track(audio_path):
    return {
        'path': str(audio_path),
        'title': 'Test Song',
        'artists': ['Test Artist'],
        'album': 'Test Album',
        'duration': 240.0,
    }


class TestPathFor:
    """lrc must land in the directory of the audio file, with the same stem"""

    def test_absolute_path(self, service, audio_path):
        assert service.path_for(str(audio_path)) == audio_path.with_suffix('.lrc')

    def test_relative_path_is_library_relative(self, service, tmp_path):
        assert service.path_for('sub/Test Song.flac') == tmp_path / 'sub' / 'Test Song.lrc'


class TestNormalizeTrack:
    """caller payload -> internal track shape (title/artists/album/duration)"""

    def test_artists_string_and_missing_duration(self):
        track = LyricService._normalize_track({
            'path': 'a/b.mp3',
            'title': '  Song  ',
            'artists': 'A/B & C',
            'album': None,
        })
        assert track['title'] == 'Song'
        assert track['artists'] == ['A', 'B', 'C']
        assert track['album'] == ''
        assert track['duration'] == 0.0
        assert 'dur' not in track

    def test_duration_is_float(self):
        track = LyricService._normalize_track({
            'path': 'a/b.mp3', 'title': 'Song', 'artists': ['A'], 'duration': '250.5',
        })
        assert track['duration'] == 250.5
        assert 'dur' not in track


class TestFetch:
    """fetch() must return a result and write the lrc after a high confidence match"""

    def test_fetch_writes_lrc_next_to_audio(self, service, audio_path):
        res = service.fetch(_track(audio_path))

        assert isinstance(res, LyricResult)
        assert res.status == 'ok'
        assert res.written is True
        assert res.source == 'netease'
        assert res.source_id == '12345'

        lrc = audio_path.with_suffix('.lrc')
        assert res.lrc_path == lrc
        assert lrc.exists()
        body = lrc.read_text(encoding='utf-8')
        assert '[ti:Test Song]' in body
        assert '[ar:Test Artist]' in body
        assert '[length:04:00]' in body
        assert '[00:01.00]first line' in body

    def test_fetch_marks_existing_fresh_lrc_as_ok(self, service, audio_path):
        '''an existing usable lyric is a success, not a skip (skip = not fetchable)'''
        lrc = audio_path.with_suffix('.lrc')
        lrc.parent.mkdir(parents=True, exist_ok=True)
        lrc.write_text('[ti:Test Song]\n[00:01.00]old line\n', encoding='utf-8')

        res = service.fetch(_track(audio_path))

        assert res.status == 'ok'
        assert res.note == 'exists'
        assert res.written is True
        assert 'old line' in lrc.read_text(encoding='utf-8')

    def test_fetch_skips_track_without_title(self, service, audio_path):
        track = _track(audio_path)
        track['title'] = ''
        res = service.fetch(track)

        assert res.status == 'skip'
        assert res.note == 'no_title'
        assert res.written is False
        assert not audio_path.with_suffix('.lrc').exists()


class TestWatcherHook:
    """the watcher queues the lyric fetch with the parsed title/artists/album/duration"""

    @staticmethod
    def _meta(audio, **overrides):
        from app.schemas.filething import ParsedMeta

        data = {
            'path': str(audio),
            'title': 'Test Song',
            'artists': ['Test Artist'],
            'album': 'Test Album',
            'albumartist': [],
            'year': 0,
            'genres': [],
            'mb_artistids': [],
            'mb_albumartistid': [],
            'mb_albumid': '',
            'mb_trackid': '',
            'acoustid_id': '',
            'duration': 240.0,
            'bitrate': 320000,
            'bitrate_mode': 'CBR',
        }
        data.update(overrides)
        return ParsedMeta.model_validate(data)

    @staticmethod
    def _mock_db():
        from unittest.mock import AsyncMock, MagicMock

        result = MagicMock()
        result.scalar_one_or_none.return_value = 1
        db = AsyncMock()
        db.execute.return_value = result
        return db

    async def test_enqueue_builds_payload_from_parsed_meta(self, monkeypatch):
        from app.background.watcher_manager import WatcherManager
        from app.core.config import settings

        manager = WatcherManager(str(settings.MUSIC_LIBRARY_PATH))
        captured = {}
        monkeypatch.setattr(manager.lyric_service, 'submit',
                            lambda track: (captured.update(track), True)[1])

        audio = settings.MUSIC_LIBRARY_PATH / 'lyric-hook-test.mp3'
        await manager._enqueue_lyric(self._mock_db(), str(audio), self._meta(audio, title=' Test Song '))

        assert captured['path'] == str(audio)
        assert captured['title'] == 'Test Song'
        assert captured['artists'] == ['Test Artist']
        assert captured['album'] == 'Test Album'
        assert captured['duration'] == 240.0

    async def test_enqueue_skips_track_without_title(self, monkeypatch):
        from app.background.watcher_manager import WatcherManager
        from app.core.config import settings

        manager = WatcherManager(str(settings.MUSIC_LIBRARY_PATH))
        monkeypatch.setattr(manager.lyric_service, 'submit',
                            lambda track: pytest.fail('submit must not be called'))

        audio = settings.MUSIC_LIBRARY_PATH / 'lyric-hook-test.mp3'
        await manager._enqueue_lyric(self._mock_db(), str(audio), self._meta(audio, title='  '))


class TestIdleExit:
    """the worker self-terminates when idle and is restarted on demand by submit()"""

    def test_worker_exits_when_idle(self, service, monkeypatch):
        monkeypatch.setattr(lyric_service_module, 'IDLE_EXIT', 0.2)
        service.start()
        assert _wait_until(lambda: service._worker is None, 3.0)

    def test_submit_restarts_worker_after_idle_exit(self, service, audio_path, monkeypatch):
        monkeypatch.setattr(lyric_service_module, 'IDLE_EXIT', 0.2)
        service.start()
        assert _wait_until(lambda: service._worker is None, 3.0)

        assert service.submit(_track(audio_path)) is True
        lrc = audio_path.with_suffix('.lrc')
        assert _wait_until(lrc.exists, 5.0)
        # empty queue again: the thread retires on its own
        assert _wait_until(lambda: service._worker is None, 3.0)


class TestScoreCandidate:
    """track and candidate share one duration key"""

    def test_duration_key_is_used(self):
        cand = {'id': 1, 'title': 'Test Song', 'artists': ['Test Artist'],
                'album': 'Test Album', 'duration': 241.0, 'cover': False}
        want = {'title': 'Test Song', 'artists': ['Test Artist'],
                'album': 'Test Album', 'duration': 240.0}
        assert score_candidate(cand, want) is not None

    def test_duration_mismatch_rejects_candidate(self):
        cand = {'id': 1, 'title': 'Test Song', 'artists': ['Test Artist'],
                'album': '', 'duration': 640.0, 'cover': False}
        want = {'title': 'Test Song', 'artists': ['Test Artist'],
                'album': '', 'duration': 240.0}
        assert score_candidate(cand, want) is None
