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

@dataclass
class SystemState:
    is_watcher_running: bool = False
    is_scanning: bool = False
    scan_progress: dict[str, int | str] | None = None

    _is_scanning_canceled: bool = False

    # artwork generation state
    is_generating_artworks: bool = False
    artwork_progress: dict[str, int | str] | None = None
    _is_artwork_gen_canceled: bool = False

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

    # ---- artwork generation state ----
    @property
    def is_artwork_gen_canceled(self):
        return self._is_artwork_gen_canceled
    @is_artwork_gen_canceled.setter
    def is_artwork_gen_canceled(self, value):
        self._is_artwork_gen_canceled = value

    def init_artwork_gen_state(self):
        self.is_generating_artworks = True
        self._is_artwork_gen_canceled = False
        self.artwork_progress = {
            'phase': '',            # current phase: 'artist_face', 'artist_portrait', 'album', 'track', 'playlist', 'done'
            'phase_total': 0,       # total items in current phase
            'phase_processed': 0,   # processed items in current phase
            'phase_generated': 0,   # newly generated in current phase
            'phase_skipped': 0,     # skipped (already cached) in current phase
            'phase_failed': 0,      # failed in current phase
            'total_generated': 0,   # grand total generated across all phases
            'total_skipped': 0,     # grand total skipped across all phases
            'total_failed': 0,      # grand total failed across all phases
            'current_item': '',     # current entity being processed
        }

    def reset_artwork_gen_state(self):
        self.is_generating_artworks = False
        self.artwork_progress = None
        self._is_artwork_gen_canceled = False

    def cancel_artwork_gen(self):
        self._is_artwork_gen_canceled = True

system_state = SystemState()