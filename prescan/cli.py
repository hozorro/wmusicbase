# -*- encoding: utf-8 -*-
'''
@File      :   cli.py
@Desc      :   CLI entry point for music library pre-scan inspection tool
'''


import typer
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from prescan.scanner import InspectScanner
from prescan.reporter import InspectReporter
from prescan.models import InspectBase
from prescan.checks import get_all_checks

app = typer.Typer(help='Music Library Pre-Scan Inspection Tool')

DEFAULT_DB_NAME = 'inspect_result.db'


def _resolve_library_path(library: Path | None) -> Path:
    '''resolve library path from CLI arg or .env config'''
    if library:
        return library.resolve()
    # fallback to settings
    try:
        from app.core.config import settings
        return settings.MUSIC_LIBRARY_PATH.resolve()
    except Exception:
        typer.echo('Error: Could not determine music library path.', err=True)
        typer.echo('Please specify --library or configure MUSIC_LIBRARY_PATH in .env', err=True)
        raise typer.Exit(code=1)


@app.command()
def scan(
    library: Path = typer.Option(None, '--library', '-l', help='音乐库目录路径 (默认使用 .env 中的 MUSIC_LIBRARY_PATH)'),
    db: Path = typer.Option(Path(DEFAULT_DB_NAME), '--db', '-d', help='检查结果 SQLite 数据库路径'),
    rescan: bool = typer.Option(False, '--rescan', '-r', help='强制重新扫描 (删除旧数据库)'),
    extensions: list[str] = typer.Option(['.mp3', '.flac'], '--ext', '-e', help='音频文件扩展名'),
):
    '''扫描音乐库并运行所有检查'''
    library_path = _resolve_library_path(library)

    if not library_path.exists():
        typer.echo(f'Error: Library path does not exist: {library_path}', err=True)
        raise typer.Exit(code=1)

    if rescan and db.exists():
        db.unlink()
        typer.echo(f'Removed old database: {db}')

    scanner = InspectScanner(library_path, db, extensions)
    scanner.run()


@app.command()
def report(
    db: Path = typer.Option(Path(DEFAULT_DB_NAME), '--db', '-d', help='检查结果数据库路径'),
    check: str = typer.Option(None, '--check', '-c', help='只显示特定检查项的结果'),
    severity: str = typer.Option(None, '--severity', '-s', help='按严重级别过滤: error/warning/info'),
    export: str = typer.Option(None, '--export', help='导出格式: csv'),
    output: Path = typer.Option(None, '--output', '-o', help='导出文件路径'),
    limit: int = typer.Option(100, '--limit', help='详情显示条数上限'),
):
    '''查看/导出检查结果报告'''
    if not db.exists():
        typer.echo(f'Error: Database not found: {db}', err=True)
        typer.echo('Run "scan" command first.', err=True)
        raise typer.Exit(code=1)

    engine = create_engine(f'sqlite:///{db}')
    with Session(engine) as session:
        # try to get library path from a track's file_path
        from prescan.models import InsTrack
        from sqlalchemy import select
        sample = session.execute(select(InsTrack.file_path).limit(1)).scalar_one_or_none()
        library_path = Path(sample).parent.parent.parent.parent if sample else Path('.')

        reporter = InspectReporter(session, library_path)

        # always show summary
        print(reporter.summary())

        # show details if filtered or no export
        if check or severity or not export:
            print(reporter.details(check_name=check, severity=severity, limit=limit))

        # export
        if export and export.lower() == 'csv':
            out_path = output or Path('inspect_issues.csv')
            count = reporter.export_csv(out_path)
            print(f'\n  Exported {count} issues to: {out_path}')


@app.command(name='list-checks')
def list_checks():
    '''列出所有可用的检查项'''
    checks = get_all_checks()
    print(f'\n  Available checks ({len(checks)}):\n')
    for cls in checks:
        print(f'    {cls.name:35s} {cls.description}')
    print()


if __name__ == '__main__':
    app()
