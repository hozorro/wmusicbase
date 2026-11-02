# -*- encoding: utf-8 -*-
'''
@File      :   logger.py
@Time      :   2025/10/20 20:06:21
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   logger system
'''


import logging
import logging.config
import sys
from app.core.config import settings

LOG_DIR = settings.LOG_DIR


def _make_streams_error_tolerant() -> None:
    '''让标准输出/错误流在遇到当前编码无法表示的字符时以替代符输出，而非抛异常

    Windows 控制台(如 cp936)或重定向输出时，日志中的部分 Unicode 字符会导致
    StreamHandler 抛出 UnicodeEncodeError 并打印 "Logging error" 堆栈。
    这里仅调整 errors 策略，不改动终端原有编码。
    '''
    for stream_name in ('stdout', 'stderr'):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, 'reconfigure', None)
        if not callable(reconfigure):
            continue
        try:
            reconfigure(errors='replace')
        except Exception:
            pass


_make_streams_error_tolerant()

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'verbose': {
            'format': '%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(lineno)d - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'app.log',
            'maxBytes': 1024 * 1024 * 2,  # 2MB
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8'
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'error.log',
            'maxBytes': 1024 * 1024 * 2,  # 2MB
            'backupCount': 5,
            'formatter': 'verbose',
            'encoding': 'utf-8'
        },
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG' if settings.DEBUG else 'INFO',
            'formatter': 'standard',
            'stream': 'ext://sys.stdout'
        }
    },
    'loggers': {
        'app': {
            'handlers': ['console', 'file', 'error_file'] if settings.DEBUG else ['file', 'error_file'],
            'level': 'DEBUG' if settings.DEBUG else 'INFO',
            'propagate': False
        },
        'uvicorn': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'uvicorn.access': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'sqlalchemy': {'level': 'WARNING', 'handlers': ['console'], 'propagate': False},
        'fastapi': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'httpx': {'level': 'INFO', 'handlers': ['console'], 'propagate': False},
        'asyncio': {'level': 'INFO', 'handlers': ['console'], 'propagate': False}
    }
}

_LOGGING_INITIALIZED = False

def is_logging_initialized() -> bool:
    root_looger = logging.getLogger()
    has_handlers = len(root_looger.handlers) > 0

    global _LOGGING_INITIALIZED

    return _LOGGING_INITIALIZED or has_handlers

def init_logging(force: bool = False):
    global _LOGGING_INITIALIZED

    # 流对象可能在上层被替换(如 uvicorn 重定向)，重新应用一次编码容错
    _make_streams_error_tolerant()

    if is_logging_initialized() and not force:
        logging.getLogger().info('Logging already initialized, skipping...')
        return
    
    try:
        logging.config.dictConfig(LOGGING_CONFIG)
        _LOGGING_INITIALIZED = True
        # logging the initial logs
        root_looger = logging.getLogger()
        root_looger.info(f'Logging initialized at {LOG_DIR}')
        root_looger.info(f'Debug mode: {settings.DEBUG}')
        root_looger.info(f'Log file: {LOG_DIR / "app.log"}')
    except Exception as e:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(LOG_DIR / 'fallback.log', encoding='utf-8')
            ]
        )
        logging.getLogger(__name__).error(f'Failed to initialize logging: {e}')

def get_logger(name: str = __name__) -> logging.Logger:
    '''get logger(default: __name__ of module)'''
    if not is_logging_initialized():
        init_logging()
    return logging.getLogger(name)

logger = get_logger()