# -*- encoding: utf-8 -*-
"""
tests/core/test_db.py
Tests for retry_deadlock, safe_async_transaction, and get_db.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.core.db import retry_deadlock, safe_async_transaction


# ===========================================================================
# retry_deadlock
# ===========================================================================

class TestRetryDeadlock:
    async def test_success_no_retry(self):
        """Function succeeds on first attempt — no retry needed."""
        @retry_deadlock(max_retries=3, delay=0.01)
        async def my_func():
            return 'ok'

        result = await my_func()
        assert result == 'ok'

    async def test_deadlock_retry_then_success(self):
        """Deadlock on first call, success on second."""
        from asyncpg.exceptions import DeadlockDetectedError
        call_count = 0

        @retry_deadlock(max_retries=3, delay=0.01)
        async def my_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise DeadlockDetectedError('deadlock')
            return 'recovered'

        result = await my_func()
        assert result == 'recovered'
        assert call_count == 2

    async def test_deadlock_max_retries_exhausted(self):
        """All retries fail with deadlock — exception propagates."""
        from asyncpg.exceptions import DeadlockDetectedError

        @retry_deadlock(max_retries=2, delay=0.01)
        async def my_func():
            raise DeadlockDetectedError('deadlock forever')

        with pytest.raises(DeadlockDetectedError):
            await my_func()

    async def test_in_failed_transaction_retry(self):
        """InFailedSQLTransactionError triggers retry."""
        from asyncpg.exceptions import InFailedSQLTransactionError
        call_count = 0

        @retry_deadlock(max_retries=3, delay=0.01)
        async def my_func(session):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise InFailedSQLTransactionError('failed tx')
            return 'done'

        mock_session = AsyncMock()
        mock_session.is_closed = MagicMock(return_value=False)
        result = await my_func(mock_session)
        assert result == 'done'
        assert call_count == 2

    async def test_non_retry_exception_propagates(self):
        """Non-deadlock exceptions propagate immediately."""
        @retry_deadlock(max_retries=3, delay=0.01)
        async def my_func():
            raise ValueError('not retryable')

        with pytest.raises(ValueError, match='not retryable'):
            await my_func()

    async def test_preserves_function_name(self):
        """@wraps should preserve the original function name."""
        @retry_deadlock()
        async def original_name():
            pass

        assert original_name.__name__ == 'original_name'


# ===========================================================================
# safe_async_transaction
# ===========================================================================

class TestSafeAsyncTransaction:
    async def test_success_commits(self):
        session = AsyncMock()
        session.is_active = True

        async def my_func():
            return 42

        result = await safe_async_transaction(session, my_func)
        assert result == 42
        session.commit.assert_awaited_once()
        session.close.assert_awaited_once()

    async def test_generic_exception_rollback(self):
        session = AsyncMock()
        session.is_active = True

        async def my_func():
            raise RuntimeError('oops')

        with pytest.raises(RuntimeError, match='oops'):
            await safe_async_transaction(session, my_func)
        session.rollback.assert_awaited_once()
        session.close.assert_awaited_once()

    async def test_deadlock_rollback(self):
        from asyncpg.exceptions import DeadlockDetectedError
        session = AsyncMock()
        session.is_active = True

        async def my_func():
            raise DeadlockDetectedError('deadlock')

        with pytest.raises(DeadlockDetectedError):
            await safe_async_transaction(session, my_func)
        session.rollback.assert_awaited_once()

    async def test_passes_args_and_kwargs(self):
        session = AsyncMock()
        session.is_active = True
        received = {}

        async def my_func(a, b, key=None):
            received['a'] = a
            received['b'] = b
            received['key'] = key
            return 'done'

        result = await safe_async_transaction(session, my_func, 1, 2, key='val')
        assert result == 'done'
        assert received == {'a': 1, 'b': 2, 'key': 'val'}
