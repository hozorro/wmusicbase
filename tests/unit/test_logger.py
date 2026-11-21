# -*- encoding: utf-8 -*-
"""
Tests for app/core/logger.py
Functions: _make_streams_error_tolerant, init_logging, is_logging_initialized, get_logger
"""

import logging
import logging.handlers
import sys
from unittest.mock import MagicMock

from app.core import logger as logger_module


class TestStreamsErrorTolerant:
    """Windows 控制台编码无法表示某些字符时，日志不应抛 UnicodeEncodeError"""

    def test_reconfigure_uses_errors_replace(self, monkeypatch):
        fake_stdout = MagicMock()
        fake_stderr = MagicMock()
        monkeypatch.setattr(sys, 'stdout', fake_stdout)
        monkeypatch.setattr(sys, 'stderr', fake_stderr)

        logger_module._make_streams_error_tolerant()

        fake_stdout.reconfigure.assert_called_once_with(errors='replace')
        fake_stderr.reconfigure.assert_called_once_with(errors='replace')

    def test_stream_without_reconfigure_is_skipped(self, monkeypatch):
        class _PlainStream:
            def write(self, text):
                return len(text)

        monkeypatch.setattr(sys, 'stdout', _PlainStream())
        monkeypatch.setattr(sys, 'stderr', _PlainStream())

        # 不应抛异常
        logger_module._make_streams_error_tolerant()

    def test_reconfigure_failure_is_swallowed(self, monkeypatch):
        fake_stdout = MagicMock()
        fake_stdout.reconfigure.side_effect = ValueError('detached stream')
        monkeypatch.setattr(sys, 'stdout', fake_stdout)

        logger_module._make_streams_error_tolerant()


class TestInitLogging:
    """init_logging / is_logging_initialized / get_logger"""

    def test_initialized_at_import(self):
        assert logger_module.is_logging_initialized() is True

    def test_get_logger_name(self):
        log = logger_module.get_logger('tests.sample')
        assert isinstance(log, logging.Logger)
        assert log.name == 'tests.sample'

    def test_force_init_attaches_file_handlers(self):
        logger_module.init_logging(force=True)
        handlers = logging.getLogger('app').handlers
        assert any(isinstance(h, logging.handlers.RotatingFileHandler) for h in handlers)

    def test_debug_flag_controls_console_handler(self):
        from app.core.config import settings

        logger_module.init_logging(force=True)
        handlers = logging.getLogger('app').handlers
        has_stream = any(
            isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
            for h in handlers
        )
        assert has_stream is settings.DEBUG
