# -*- encoding: utf-8 -*-
'''
@File      :   log_service.py
@Time      :   2025/12/03 16:53:51
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   log manager
'''



from pathlib import Path
from datetime import datetime
from app.core.config import settings

class LogService:
    @staticmethod
    def get_log_file_paths(log_type: str = 'app') -> list[Path]:
        '''
        get log file paths list(descending)
        log_type: log type
        '''
        log_prefix = 'app.log' if log_type == 'app' else 'error.log'
        log_files = []
        # match all log files, including rotated files, but not including .lock temp file
        for file in settings.LOG_DIR.glob(f'{log_prefix}*'):
            if not file.name.endswith('.lock'):
                log_files.append(file.absolute())

        log_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return log_files
    
    @staticmethod
    def parse_log_line(line: str) -> dict[str, str] | None:
        """
        parse log lines(match verbose format)
        verbose format: 2025-08-20 15:30:00 - INFO - app.core.logger - main.py:10 - App started.
        line: log line
        """
        try:
            # split by ' - ', limit split times to 4, to avoid matching ' - ' in message
            parts = line.split(' - ', 4)
            if len(parts) != 5: 
                return None
            
            return {
                'time': parts[0],
                'level': parts[1],
                'logger': parts[2],
                'location': parts[3],
                'message': parts[4]
            }
        except Exception:
            return None
        
    @staticmethod
    def read_logs(
        log_type: str = 'app',
        level: str | None = None,
        keyword: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        page: int = 1,
        page_size: int = 50
    ) -> tuple[list[dict[str, str]], int]:
        """
        read and filter logs(support pagination, level, keyword, and time range filtering)
        log_type: log type
        level: log level
        keyword: key word
        start_time: start time
        end_time: end time
        page: page number
        page_size: page size
        """
        log_files = LogService.get_log_file_paths(log_type)
        all_logs: list[dict[str, str]] = []
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None

        # read log files match filter conditions
        for file in log_files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()[::-1]
                    for line in lines:
                        log = LogService.parse_log_line(line)
                        if not log: 
                            continue

                        if level and log['level'].upper() != level.upper(): 
                            continue

                        if keyword and keyword.lower() not in log['message'].lower() and keyword.lower() not in log['location'].lower():
                            continue

                        log_dt = datetime.strptime(log['time'], '%Y-%m-%d %H:%M:%S')
                        if start_dt and log_dt < start_dt: 
                            continue
                        if end_dt and log_dt > end_dt: 
                            continue

                        all_logs.append(log)

                        # stop when enough logs are collected
                        if len(all_logs) >= page_size * page: 
                            break
            except Exception as e:
                print(f'Error reading log file {file}: {e}')
                continue
        total = len(all_logs)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_logs = all_logs[start:end]

        return paginated_logs, total
    
    @staticmethod
    def export_logs(
        log_type: str = 'app',
        level: str | None = None,
        keyword: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> str:
        """
        export filtered logs to a file for download(support pagination, level, keyword, and time range filtering)
        """
        logs, _ = LogService.read_logs(
            log_type=log_type,
            level=level,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
            page=1,
            page_size=10000
        )
        log_lines = [
            f"{log['time']}[{log['level']}][{log['logger']}][{log['location']}]: {log['message']}"
            for log in logs
        ]
        return '\n'.join(log_lines)

