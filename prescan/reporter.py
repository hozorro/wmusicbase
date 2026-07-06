# -*- encoding: utf-8 -*-
'''
@File      :   reporter.py
@Desc      :   Inspection report formatter and exporter
'''


import csv
from pathlib import Path
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from prescan.models import InsTrack, InsArtist, InsAlbum, InsGenre, InsIssue
from prescan.checks import get_all_after_checks


# ANSI color codes
_COLORS = {
    'error': '\033[91m',    # red
    'warning': '\033[93m',  # yellow
    'info': '\033[94m',     # blue
    'reset': '\033[0m',
    'bold': '\033[1m',
    'dim': '\033[2m',
}


def _c(text: str, color: str) -> str:
    '''wrap text with ANSI color'''
    return f'{_COLORS.get(color, "")}{text}{_COLORS["reset"]}'


class InspectReporter:
    '''format and output inspection results'''

    def __init__(self, session: Session, library_path: Path):
        self.session = session
        self.library_path = library_path

    def summary(self) -> str:
        '''generate summary report'''
        # counts
        track_count = self.session.execute(select(func.count(InsTrack.id))).scalar() or 0
        artist_count = self.session.execute(select(func.count(InsArtist.id))).scalar() or 0
        album_count = self.session.execute(select(func.count(InsAlbum.id))).scalar() or 0
        genre_count = self.session.execute(select(func.count(InsGenre.id))).scalar() or 0
        issue_count = self.session.execute(select(func.count(InsIssue.id))).scalar() or 0

        # group by severity
        severity_rows = self.session.execute(
            select(InsIssue.severity, func.count(InsIssue.id))
            .group_by(InsIssue.severity)
        ).all()
        severity_map = {row[0]: row[1] for row in severity_rows}

        # group by check_name
        check_rows = self.session.execute(
            select(InsIssue.check_name, InsIssue.severity, func.count(InsIssue.id))
            .group_by(InsIssue.check_name, InsIssue.severity)
            .order_by(func.count(InsIssue.id).desc())
        ).all()

        lines = []
        lines.append('')
        lines.append(_c('═' * 60, 'bold'))
        lines.append(_c('  Music Library Pre-Scan Inspection Report', 'bold'))
        lines.append(_c('═' * 60, 'bold'))
        lines.append(f'  Library:      {self.library_path}')
        lines.append(f'  Artists:      {artist_count}')
        lines.append(f'  Albums:       {album_count}')
        lines.append(f'  Tracks:       {track_count}')
        lines.append(f'  Genres:       {genre_count}')
        lines.append('')
        lines.append(f'  Total Issues: {_c(str(issue_count), "bold")}')
        lines.append('')

        # by severity
        lines.append('  By Severity:')
        for sev in ['error', 'warning', 'info']:
            count = severity_map.get(sev, 0)
            color = sev
            lines.append(f'    {_c(sev.upper(), color):>24s}: {count}')
        lines.append('')

        # by check
        if check_rows:
            lines.append('  By Check:')
            for check_name, severity, count in check_rows:
                lines.append(f'    {check_name:40s}: {_c(str(count), severity)} ({severity})')

        lines.append('')
        lines.append(_c('═' * 60, 'bold'))
        return '\n'.join(lines)

    def details(self, check_name: str | None = None, severity: str | None = None,
                limit: int = 100) -> str:
        '''show detailed issues, optionally filtered'''
        stmt = select(InsIssue).order_by(InsIssue.severity, InsIssue.check_name)
        if check_name:
            stmt = stmt.where(InsIssue.check_name == check_name)
        if severity:
            stmt = stmt.where(InsIssue.severity == severity)
        stmt = stmt.limit(limit)

        issues = self.session.execute(stmt).scalars().all()
        if not issues:
            return '  No issues found matching the filter.'

        lines = []
        lines.append(f'\n  Showing {len(issues)} issues:\n')
        for issue in issues:
            sev_color = issue.severity
            badge = _c(f'[{issue.severity.upper():>7s}]', sev_color)
            lines.append(f'  {badge} {issue.message}')
            if issue.file_path:
                lines.append(f'          {_c(issue.file_path, "dim")}')
            if issue.detail:
                lines.append(f'          Detail: {issue.detail}')

        if len(issues) == limit:
            lines.append(f'\n  {_c(f"... and more (showing first {limit})", "dim")}')
        return '\n'.join(lines)

    def export_csv(self, output_path: Path) -> int:
        '''export all issues to CSV, return row count'''
        issues = self.session.execute(
            select(InsIssue).order_by(InsIssue.severity, InsIssue.check_name)
        ).scalars().all()

        with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'check_name', 'severity', 'entity_type', 'entity_id',
                             'file_path', 'message', 'detail'])
            for issue in issues:
                writer.writerow([
                    issue.id, issue.check_name, issue.severity, issue.entity_type,
                    issue.entity_id, issue.file_path, issue.message, issue.detail
                ])
        return len(issues)

    def run_after_checks(self, check_name: str | None = None,
                         export: str | None = None, output_path: Path | None = None) -> str:
        '''run after-checks directly without re-scanning'''
        after_checks = get_all_after_checks()
        if not after_checks:
            return '  No after-checks registered.'

        lines = []
        lines.append('')
        lines.append(_c('═' * 60, 'bold'))
        lines.append(_c('  After-Checks Results (Live)', 'bold'))
        lines.append(_c('═' * 60, 'bold'))
        lines.append('')

        total_issues = 0
        for check_cls in after_checks:
            if check_name and check_cls.name != check_name:
                continue

            check = check_cls(self.session, self.library_path)
            issues = check.run()
            total_issues += len(issues)

            lines.append(f'  {_c(check_cls.name, "bold")}: {check_cls.description}')
            lines.append(f'    Found {_c(str(len(issues)), "warning")} issues')

            # terminal: only statistics, no detail lines
            if issues:
                for issue in issues[:5]:
                    badge = _c(f'[{issue.severity.upper():>7s}]', issue.severity)
                    lines.append(f'    {badge} {issue.message}')
            lines.append('')

            # CSV export
            if export and export.lower() == 'csv' and hasattr(check, 'export_csv'):
                out = output_path or Path(f'd:/{check_cls.name}.csv')
                row_count = check.export_csv(out)
                lines.append(f'    {_c("Exported", "green")} {row_count} rows -> {out}')
                lines.append('')

        lines.append(f'  Total after-check issues: {_c(str(total_issues), "bold")}')
        lines.append(_c('═' * 60, 'bold'))
        return '\n'.join(lines)
