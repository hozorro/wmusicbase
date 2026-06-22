# -*- encoding: utf-8 -*-
'''
@File      :   database.py
@Desc      :   SQLite engine setup for inspection tool
'''


from pathlib import Path
from sqlalchemy import create_engine, text, Engine


def create_inspect_engine(db_path: Path) -> Engine:
    '''create a synchronous SQLite engine with performance-optimized PRAGMAs'''
    engine = create_engine(
        f'sqlite:///{db_path}',
        echo=False,
        connect_args={'check_same_thread': False},
    )
    with engine.connect() as conn:
        conn.execute(text('PRAGMA journal_mode=WAL'))
        conn.execute(text('PRAGMA synchronous=NORMAL'))
        conn.execute(text('PRAGMA cache_size=-64000'))  # 64MB cache
        conn.commit()
    return engine
