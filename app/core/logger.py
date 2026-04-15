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
from app.core.config import settings

LOG_DIR = settings.LOG_DIR

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
                logging.FileHandler(LOG_DIR / 'fallback.log')
            ]
        )
        logging.getLogger(__name__).error(f'Failed to initialize logging: {e}')

def get_logger(name: str = __name__) -> logging.Logger:
    '''get logger(default: __name__ of module)'''
    if not is_logging_initialized():
        init_logging()
    return logging.getLogger(name)

logger = get_logger()