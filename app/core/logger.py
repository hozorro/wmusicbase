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
import logging.handlers
from pathlib import Path
from app.core.config import settings

def setup_logging():
    '''配置日志系统'''
    log_dir = settings.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    # 格式化器
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 1. 主日志（INFO及以上）
    app_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / 'app.log',
        maxBytes=1024 * 1024 * 2,  # 2MB
        backupCount=5,
        encoding='utf-8'
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)

    # 2. 错误日志（ERROR及以上）
    error_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / 'error.log',
        maxBytes=1024 * 1024 * 2,  # 2MB
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    # 3. 调试日志（DEBUG及以上，仅当DEBUG=True时启用）
    if settings.DEBUG:
        debug_handler = logging.handlers.RotatingFileHandler(
            filename=log_dir / 'debug.log',
            maxBytes=1024 * 1024 * 5,  # 5MB
            backupCount=5,
            encoding='utf-8'
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(formatter)

    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    root_logger.addHandler(app_handler)
    root_logger.addHandler(error_handler)
    if settings.DEBUG: 
        root_logger.addHandler(debug_handler)

    # 禁用第三方库的DEBUG日志（如asyncio, sqlalchemy.engine）
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)