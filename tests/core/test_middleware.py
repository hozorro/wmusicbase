# -*- encoding: utf-8 -*-
"""
tests/core/test_middleware.py
Tests for ScanMiddleware.
"""

from unittest.mock import AsyncMock, patch

from app.core.middleware import ScanMiddleware, ALLOWED_DURING_SCAN


def _make_scope(path='/api/v1/music/tracks'):
    return {
        'type': 'http',
        'path': path,
        'headers': [],
        'query_string': b'',
        'method': 'GET',
    }


class TestScanMiddleware:
    async def test_non_http_passes_through(self):
        app = AsyncMock()
        mw = ScanMiddleware(app)
        scope = {'type': 'websocket'}
        await mw(scope, AsyncMock(), AsyncMock())
        app.assert_awaited_once()

    async def test_not_scanning_passes_through(self):
        app = AsyncMock()
        mw = ScanMiddleware(app)
        scope = _make_scope()
        with patch('app.core.middleware.system_state') as mock_state:
            mock_state.is_scanning = False
            await mw(scope, AsyncMock(), AsyncMock())
        app.assert_awaited_once()

    async def test_scanning_blocked_path(self):
        app = AsyncMock()
        mw = ScanMiddleware(app)
        scope = _make_scope('/api/v1/music/tracks')
        with patch('app.core.middleware.system_state') as mock_state:
            mock_state.is_scanning = True
            receive = AsyncMock()
            send = AsyncMock()
            await mw(scope, receive, send)
        # app should NOT be called — 423 response returned instead
        app.assert_not_awaited()
        # send should have been called with 423 status
        assert send.await_count >= 1

    async def test_scanning_allowed_path(self):
        app = AsyncMock()
        mw = ScanMiddleware(app)
        for path in ALLOWED_DURING_SCAN:
            scope = _make_scope(path)
            with patch('app.core.middleware.system_state') as mock_state:
                mock_state.is_scanning = True
                await mw(scope, AsyncMock(), AsyncMock())
        # app should be called for each allowed path
        assert app.await_count == len(ALLOWED_DURING_SCAN)
