# -*- encoding: utf-8 -*-
'''
@File      :   cli.py
@Time      :   2026/02/07 21:18:19
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2026 WEYECO <enauvy@qq.com>
@Desc      :   cli
'''


import typer
from pathlib import Path
from alembic import command
from alembic.config import Config
from app.core.config import create_required_directories

app = typer.Typer()

def get_alembic_config() -> Config:
    '''get alembic config'''
    base_path = Path(__file__).resolve().parent.parent
    alembic_ini_path = base_path / 'alembic.ini'
    if not alembic_ini_path.exists():
        raise FileNotFoundError('alembic.ini not found')
    cfg = Config(str(alembic_ini_path))
    cfg.set_main_option('script_location', str(base_path / 'alembic'))
    return cfg

@app.command()
def init_dirs():
    '''init required directories'''
    create_required_directories()
    typer.echo('Required directories initialized successfully.')

@app.command()
def init_db():
    '''init database'''
    cfg = get_alembic_config()
    command.upgrade(cfg, 'head')
    typer.echo('Database initialized / upgraded successfully.')

@app.command()
def downgrade_db(revision: str = 'base'):
    '''downgrade database to a specific revision (default: base)'''
    cfg = get_alembic_config()
    command.downgrade(cfg, revision)
    typer.echo(f'Database downgraded to revision {revision} successfully.')

if __name__ == "__main__":
    app()
