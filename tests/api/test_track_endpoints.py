# -*- encoding: utf-8 -*-
"""
tests/api/test_track_endpoints.py
新增音乐端点（全部曲目分页 / 新鲜模式 / 4 个高级随机端点）与首页条数口径的契约测试。

用 dependency_overrides 顶掉 TrackService 与登录门禁，只验证路由注册、参数契约、
响应形状与前端 SW/IDB 的口径一致性；SQL 本身不连数据库。
"""
import inspect
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.db import get_db
from app.core.deps import require_login
from app.services.track_service import (
    TrackService,
    HOME_TRACK_COUNT,
    clamp_tracks_num,
    normalize_pool,
    clamp_weight,
    weight_alpha,
    weighted_sample,
)

BASE = '/api/v1/music/track'


def brief(i: int):
    """TrackBrief.model_validate 可接受的最小 ORM 形状替身"""
    return SimpleNamespace(
        id=i,
        title=f'T{i}',
        cover_art_hash=None,
        duration=120.0,
        album=SimpleNamespace(id=1, title='Album'),
        artists=[SimpleNamespace(id=1, name='Artist')],
    )


@pytest.fixture
def mock_service():
    svc = MagicMock(spec=TrackService)
    for name in (
        'get_latest_added_tracks',
        'get_most_played_tracks',
        'get_sorted_tracks',
        'get_rnd_fresh_tracks',
        'get_rnd_artist_scattered_tracks',
        'get_rnd_unhit_tracks',
        'get_rnd_weighted_artist_tracks',
        'get_rnd_weighted_hit_tracks',
    ):
        setattr(svc, name, AsyncMock(return_value=[]))
    svc.get_sorted_tracks.return_value = (0, [])
    return svc


@pytest.fixture
def client(mock_service, mock_db):
    async def _override_db():
        yield mock_db

    async def _override_login(request: Request):
        request.state.user_id = 1

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[require_login] = _override_login
    app.dependency_overrides[TrackService] = lambda: mock_service
    yield AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=True),
        base_url='http://test',
    )
    app.dependency_overrides.clear()


class TestHomepageTrackCount:
    """后端默认 12 与前端本地 IDB 固定 16 的历史差异已统一"""

    def test_constant_and_service_defaults(self):
        assert HOME_TRACK_COUNT == 16
        assert inspect.signature(TrackService.get_latest_added_tracks).parameters['num'].default == HOME_TRACK_COUNT
        assert inspect.signature(TrackService.get_most_played_tracks).parameters['limit'].default == HOME_TRACK_COUNT

    async def test_latesttracks_default_is_16(self, client, mock_service):
        mock_service.get_latest_added_tracks.return_value = [brief(1)]
        resp = await client.get(f'{BASE}/latesttracks')
        assert resp.status_code == 200
        assert resp.json()['code'] == 200
        assert resp.json()['data'][0]['id'] == 1
        mock_service.get_latest_added_tracks.assert_awaited_once_with(16)

    async def test_mostplayedtracks_default_is_16(self, client, mock_service):
        resp = await client.get(f'{BASE}/mostplayedtracks')
        assert resp.status_code == 200
        mock_service.get_most_played_tracks.assert_awaited_once_with(16)

    async def test_num_param_is_forwarded(self, client, mock_service):
        await client.get(f'{BASE}/latesttracks?num=5')
        await client.get(f'{BASE}/mostplayedtracks?num=7')
        mock_service.get_latest_added_tracks.assert_awaited_once_with(5)
        mock_service.get_most_played_tracks.assert_awaited_once_with(7)


class TestTracksPageEndpoint:
    async def test_full_contract(self, client, mock_service):
        mock_service.get_sorted_tracks.return_value = (42, [brief(7)])
        resp = await client.get(f'{BASE}/tracks?sort=history&page=2&page_size=10')
        assert resp.status_code == 200
        assert resp.json()['data'] == {
            'total': 42,
            'page': 2,
            'page_size': 10,
            'sort': 'history',
            'tracks': [{
                'id': 7,
                'title': 'T7',
                'cover_art_hash': None,
                'duration': 120.0,
                'album': {'id': 1, 'title': 'Album'},
                'artists': [{'id': 1, 'name': 'Artist'}],
            }],
        }
        mock_service.get_sorted_tracks.assert_awaited_once_with('history', 2, 10)

    async def test_defaults(self, client, mock_service):
        await client.get(f'{BASE}/tracks')
        mock_service.get_sorted_tracks.assert_awaited_once_with('latest', 1, 20)

    async def test_invalid_sort_and_paging_are_rejected(self, client):
        for query in ('sort=nope', 'page=0', 'page_size=0', 'page_size=101'):
            resp = await client.get(f'{BASE}/tracks?{query}')
            assert resp.status_code == 422, query


class TestAdvancedRandomEndpoints:
    async def test_rndfreshtracks_clamps_and_rounds_pool(self, client, mock_service):
        mock_service.get_rnd_fresh_tracks.return_value = [brief(3)]
        resp = await client.get(f'{BASE}/rndfreshtracks?num=7&pool=250')
        assert resp.status_code == 200
        assert resp.json()['data'][0]['id'] == 3
        # 250 / 100 = 2.5，half-up → 300（与 JS Math.round 一致）
        mock_service.get_rnd_fresh_tracks.assert_awaited_once_with(7, 300)

    async def test_rndartisttracks_forwards_num_and_numpa(self, client, mock_service):
        await client.get(f'{BASE}/rndartisttracks?num=50&numpa=3')
        mock_service.get_rnd_artist_scattered_tracks.assert_awaited_once_with(50, 3)

    async def test_rndunhittracks_forwards_num(self, client, mock_service):
        await client.get(f'{BASE}/rndunhittracks?num=12')
        mock_service.get_rnd_unhit_tracks.assert_awaited_once_with(12)

    async def test_rndwgttracks_forwards_num_and_weight(self, client, mock_service):
        await client.get(f'{BASE}/rndwgttracks?num=10&weight=7')
        mock_service.get_rnd_weighted_artist_tracks.assert_awaited_once_with(10, 7)

    async def test_rndhitswgttracks_forwards_num_and_weight(self, client, mock_service):
        await client.get(f'{BASE}/rndhitswgttracks?num=10&weight=3')
        mock_service.get_rnd_weighted_hit_tracks.assert_awaited_once_with(10, 3)

    async def test_all_advanced_endpoints_return_flattened_track_list(self, client, mock_service):
        """前端 Random.vue 直接 toPlayTrack(...)，不能是 {artist, tracks} 包装形状"""
        for name in (
            'get_rnd_fresh_tracks',
            'get_rnd_artist_scattered_tracks',
            'get_rnd_unhit_tracks',
            'get_rnd_weighted_artist_tracks',
            'get_rnd_weighted_hit_tracks',
        ):
            getattr(mock_service, name).return_value = [brief(1)]
        for path in (
            '/rndfreshtracks', '/rndartisttracks', '/rndunhittracks',
            '/rndwgttracks', '/rndhitswgttracks',
        ):
            resp = await client.get(f'{BASE}{path}')
            assert resp.status_code == 200, path
            data = resp.json()['data']
            assert isinstance(data, list) and data[0]['id'] == 1, path
            assert 'artist' not in data[0] and 'tracks' not in data[0], path


class TestRouteOrder:
    def test_static_routes_are_declared_before_dynamic_track_id(self):
        from app.api.v1.music.track import router
        paths = [r.path for r in router.routes]
        dynamic = paths.index('/{track_id:int}')
        for path in (
            '/tracks', '/rndfreshtracks', '/rndartisttracks',
            '/rndunhittracks', '/rndwgttracks', '/rndhitswgttracks',
        ):
            assert paths.index(path) < dynamic, path


class TestRandomParamsParity:
    """与前端 idb/sw-api/endpoints/tracks.ts 的夹取/取整口径对齐"""

    def test_clamp_tracks_num(self):
        assert clamp_tracks_num(0) == 1
        assert clamp_tracks_num(999) == 200
        assert clamp_tracks_num(3) == 3

    def test_normalize_pool_half_up(self):
        assert normalize_pool(50) == 100
        assert normalize_pool(149) == 100
        assert normalize_pool(150) == 200
        assert normalize_pool(250) == 300
        assert normalize_pool(9999) == 1000

    def test_weight_clamp_and_alpha(self):
        assert clamp_weight(0) == 2 and clamp_weight(99) == 9
        assert weight_alpha(2) == 0.25
        assert weight_alpha(5) == 1
        assert weight_alpha(9) == 2
        assert weight_alpha(99) == 2

    def test_weighted_sample_unique_and_bounded(self):
        random.seed(0)
        picked = weighted_sample([(i, 1.0) for i in range(10)], 3)
        assert len(picked) == 3
        assert len(set(picked)) == 3
        assert weighted_sample([], 3) == []


class TestServiceShortCircuit:
    @staticmethod
    def _service(result):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)
        request = SimpleNamespace(state=SimpleNamespace(user_id=1))
        return TrackService(db=db, settings=MagicMock(), request=request), db

    async def test_sorted_tracks_beyond_total_returns_empty_page(self):
        result = MagicMock()
        result.scalar_one.return_value = 3
        service, db = self._service(result)
        assert await service.get_sorted_tracks('latest', 10, 20) == (3, [])
        assert db.execute.await_count == 1

    async def test_rnd_fresh_tracks_empty_library_returns_empty_list(self):
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        service, db = self._service(result)
        assert await service.get_rnd_fresh_tracks(50, 500) == []
        assert db.execute.await_count == 1


class _FakeResult:
    """让每个 service 方法都走完整分支，同时把生成的 SQL 交给调用方编译"""

    def __init__(self, item, row):
        self.item = item
        self.row = row

    def scalars(self):
        return SimpleNamespace(all=lambda: [self.item], first=lambda: self.item)

    def all(self):
        return [self.row]

    def scalar_one(self):
        return 100


class TestServiceSqlCompiles:
    async def test_all_statements_compile_for_postgresql(self):
        from sqlalchemy.dialects import postgresql

        fake = _FakeResult(
            brief(1),
            SimpleNamespace(artist_id=1, track_count=2, id=1, hit_count=0),
        )
        db = AsyncMock()
        db.execute = AsyncMock(return_value=fake)
        service = TrackService(
            db=db,
            settings=MagicMock(),
            request=SimpleNamespace(state=SimpleNamespace(user_id=1)),
        )

        for sort in ('latest', 'hot', 'history'):
            await service.get_sorted_tracks(sort, 1, 20)
        await service.get_rnd_fresh_tracks(50, 500)
        await service.get_rnd_artist_scattered_tracks(50, 1)
        await service.get_rnd_unhit_tracks(50)
        await service.get_rnd_weighted_artist_tracks(50, 5)
        await service.get_rnd_weighted_hit_tracks(50, 5)

        assert db.execute.await_count >= 10
        dialect = postgresql.dialect()
        for call in db.execute.await_args_list:
            sql = str(call.args[0].compile(dialect=dialect))
            assert 'SELECT' in sql
