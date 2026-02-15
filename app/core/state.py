# -*- encoding: utf-8 -*-
'''
@File      :   state.py
@Time      :   2025/10/23 22:45:36
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   system states
'''


from dataclasses import dataclass

init_progress = {
    'total': 0,
    'processed': 0,
    'success': 0,
    'failed': 0,
    'current_file': ''
}

@dataclass
class SystemState:
    is_watcher_running: bool = False
    is_scanning: bool = False
    scan_progress: dict[str, int | str] | None = None

    _is_scanning_canceled: bool = False

    @property
    def is_scanning_canceled(self):
        return self._is_scanning_canceled
    @is_scanning_canceled.setter
    def is_scanning_canceled(self, value):
        self._is_scanning_canceled = value

    def init_scan_state(self):
        self.is_scanning = True
        self._is_scanning_canceled = False
        self.scan_progress = {
            'total': 0,
            'processed': 0,
            'success': 0,
            'failed': 0,
            'current_file': ''
        }
    
    def reset_scan_state(self):
        self.is_scanning = False
        self.scan_progress = None
        self._is_scanning_canceled = False

    def cancel_scan(self):
        self._is_scanning_canceled = True

system_state = SystemState()