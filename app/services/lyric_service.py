# -*- encoding: utf-8 -*-
'''
@File      :   lyric_service.py
@Time      :   2026/10/20 20:10:02
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   deal lyric of track
'''


import re, unicodedata, difflib, threading, time, json
import socket
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlparse, urlencode
from app.core.config import Settings
from app.core.logger import get_logger

logger = get_logger(__name__)

try:
    from opencc import OpenCC
    _CC = OpenCC('t2s')
    _SIMP = lambda s: _CC.convert(s)
    _SIMP_SRC = 'opencc'
except ImportError:
    _SIMP = lambda s: s
    _SIMP_SRC = 'none'

UA = 'lrc-fetch-service/1.0 (personal library tool)'
UNKNOWN_ARTIST = {'群星', 'various artists', 'various', '未知', '未知歌手', '合辑', '精选'}

NETEASE_REQ_GAP = 31
NETEASE_LIMIT_CODE = 405
FALLBACK_REQ_GAP = 10
NET_TIMEOUT = 25
COOL_DOWN = 1200
COOL_DOWN_MAX = 3
# The worker thread terminates itself after this many idle seconds (empty queue,
# nothing in flight), the next submit() starts a fresh one. A thread resident for
# the whole life of the process is pointless for a service that only works when
# files change; 30 min is far above the gap between two files of the same album.
IDLE_EXIT = 1800
LENIENT_DURATION = 0.0
PAGE_CANDIDATES_COUNT = 100
PAGES = 2
WRITE_REVIEW = True

# --------------------------------------------------------------------------
# Text normalization
# --------------------------------------------------------------------------
BRACKET = re.compile(r'[\(（\[\{【][^\)）\]\}】]*[\)）\]\}】]')
LOCAL_MARK = re.compile(r'\[\s*(?:粤|国|音|韩|日|英|台|闽|现场|伴奏|纯音乐)\s*\]')
TRACK_NO = re.compile(r'^\s*(?:\d{1,2}[-.]\d{1,3}|\d{1,3})\s+')
JUNK_TITLE = re.compile(
    r'(?i)(dj|remix|rmx|伴奏|纯音乐|伴唱|karaoke|instrumental|cover|翻唱|原唱|'
    r'unplugged|acoustic|重制|remaster|radio\s*edit|extended|夜店|慢摇)')
VERSION_MARK = re.compile(
    r'(?i)(国语版|粤语版|日语版|英文版|韩语版|闽南语版|live|现场版|演唱会版|'
    r'demo|钢琴版|吉他版|纯音乐版|演奏版)')
TS = re.compile(r'\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]')
PLACEHOLDER = re.compile(r'纯音乐|请欣赏|没有填词|暂无歌词|无歌词|not\s*found|歌詞|歌词贡献者')
META_LINE = re.compile(
    r'^\s*\[(id|hash|sign|qq|total|kana|language|ve|ti|ar|al|by|re|length)\s*:.*\]\s*$', re.I)

def to_simp(s):
    return _SIMP(s) if s else s

def strip_marks(s):
    if not s:
        return ''
    s = LOCAL_MARK.sub(' ', s)
    s = TRACK_NO.sub('', s)
    return re.sub(r'\s+', ' ', s).strip()

def clean_title(s):
    if not s:
        return ''
    s = strip_marks(to_simp(s))
    s = BRACKET.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip(' -–—.')

def norm_key(s):
    if not s:
        return ''
    # NFKC 必须先做：全角/半角、･(U+FF65)→・(U+30FB) 不归一，
    # 「P・A・R・A・D・O・X」与「P･A･R･A･D･O･X」只有 0.54 相似度，会直接进否决。
    s = unicodedata.normalize('NFKC', strip_marks(to_simp(s))).lower()
    s = BRACKET.sub('', s)
    return re.sub(r'[\s\-_·．.,，、\'"“”‘’!！?？:：/\\+&＆～~^]', '', s)

def split_artists(s):
    if not s:
        return []
    if isinstance(s, (list, tuple)):
        vals = [str(x) for x in s if str(x).strip()]
    else:
        s = to_simp(str(s))
        vals = re.split(r'\s*(?:/|、|,|;|&|＆|\+|\bfeat\.?|\bft\.?|\sx\s)\s*', s, flags=re.I)
    return [v.strip() for v in vals if v and v.strip()]

def sim(a, b):
    ka, kb = norm_key(a), norm_key(b)
    if not ka or not kb:
        return 0.0
    if ka == kb:
        return 1.0
    if ka in kb or kb in ka:
        base = min(len(ka), len(kb)) / max(len(ka), len(kb))
        return max(0.88, base)
    return difflib.SequenceMatcher(None, ka, kb).ratio()

def mmss(sec):
    sec = int(round(sec or 0))
    return f'{sec // 60:02d}:{sec % 60:02d}'

# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------
def dur_score(delta):
    if delta is None:
        return 0.5
    a = abs(delta)
    if a <= 2:
        return 1.0
    if a <= 5:
        return 0.6
    if a <= 10:
        return 0.2
    return 0.0

def artists_score(want, cand, cand_alias=None):
    """Exact match 1.0 / Contains 0.5 / Not match 0.0.

    cand_alias is the official alias (A-Lin ↔ 黄丽玲, G.E.M. ↔ 邓紫棋). Local tags
    common stage names, NetEase Cloud returns the birth name, not the alias, whole batch of songs will be judged asc=0 and sunk to low.
    """
    want = [w for w in want if w]
    cand = [c for c in cand if c]
    if not want or not cand:
        return 0.5
    if all(norm_key(w) in UNKNOWN_ARTIST for w in want):
        return 0.5
    wk = {norm_key(w) for w in want if norm_key(w)}
    ck = {norm_key(c) for c in cand if norm_key(c)}
    if wk & ck:
        return 1.0
    ak = {norm_key(x) for x in (cand_alias or []) if norm_key(x)}
    if wk & ak:
        return 1.0
    if any(len(k) >= 2 and (k in c or c in k) for k in wk for c in ck):
        return 0.5
    return 0.0

def score_candidate(cand, track, lenient_dur=0.0):
    """Return (score, conf, detail) or None (hard rejection)."""
    tsim = sim(clean_title(cand['title']), track['title'])
    if tsim < 0.82:
        return None
    delta = None
    want_dur = track.get('duration')
    if want_dur and cand.get('duration'):
        delta = cand['duration'] - want_dur
        if abs(delta) > 10:
            return None
        dsc = dur_score(delta)
    else:
        dsc = 0.5
    asc = artists_score(track['artists'], cand['artists'], cand.get('artist_alias'))
    album_sim = sim(cand.get('album', ''), track.get('album', '')) if track.get('album') else 0.0
    wk = {norm_key(w) for w in track['artists'] if w}
    ck = {norm_key(c) for c in cand['artists'] if c}
    by_alias = 1 if asc == 1.0 and wk and not (wk & ck) else 0

    s = 3.0 * tsim
    if tsim >= 0.999:
        s += 1.0
    s += 2.5 * asc
    s += 1.5 * album_sim if album_sim >= 0.8 else 0.6 * album_sim
    s += 3.0 * dsc
    if JUNK_TITLE.search(cand['title']) and not JUNK_TITLE.search(track['title'] or ''):
        s -= 2.5
    if VERSION_MARK.search(cand['title']) and not VERSION_MARK.search(track['title'] or ''):
        s -= 1.5
    if cand.get('cover'):
        s -= 2.0

    lenient = 0
    if tsim >= 0.95 and asc == 1.0 and dsc >= 1.0:
        conf = 'high'
    elif lenient_dur > 0 and tsim >= 0.95 and asc == 1.0 and delta is not None \
            and abs(delta) <= lenient_dur:
        conf = 'medium'
        lenient = 1
    elif tsim >= 0.85 and asc >= 0.5 and dsc >= 0.5:
        conf = 'medium'
    else:
        conf = 'low'
    return round(s, 2), conf, {
        'tsim': round(tsim, 3), 'asc': asc, 'dsc': dsc, 'alias': by_alias,
        'album': round(album_sim, 2), 'lenient': lenient,
        'dt': round(delta, 1) if delta is not None else None,
    }

def parse_candidates(songs):
    """Parse candidates from /cloudsearch or /search into internal candidates."""
    out = []
    for s in songs:
        if 'artists' in s:                     # /search shape
            ars = s.get('artists') or []
            alb = (s.get('album') or {}).get('name', '')
            dur = (s.get('duration') or 0) / 1000.0
        else:                                  # /cloudsearch shape
            ars = s.get('ar') or []
            alb = (s.get('al') or {}).get('name', '')
            dur = (s.get('dt') or 0) / 1000.0
        alias = []
        for a in ars:
            for key in ('alias', 'alia'):
                for x in a.get(key) or []:
                    if x and x not in alias:
                        alias.append(x)
        out.append({
            'id': s.get('id'), 'title': s.get('name', ''),
            'artists': [a.get('name', '') for a in ars],
            'artist_alias': alias, 'album': alb, 'duration': round(dur, 1),
            'cover': bool(s.get('originSongSimpleData')), 'status': s.get('status', 1),
        })
    return out

def parse_lrc_head(txt):
    """Parse LRC head into a dictionary.""" 
    head = {}
    for k, pat in (('title', r'^\[ti:(.*?)\]'), ('artist', r'^\[ar:(.*?)\]'),
                   ('album', r'^\[al:(.*?)\]')):
        m = re.search(pat, txt, re.M)
        if m and m.group(1).strip():
            head[k] = m.group(1).strip()
    m = re.search(r'^\[total:(\d+(?:\.\d+)?)\]', txt, re.M)
    d = float(m.group(1)) if m else 0.0
    head['dur'] = d if 0 < d < 3600 else 0.0
    return head

def validate_lyric(txt):
    """Return (lyric, why). why=placeholder is pure music placeholder, empty/too_short is empty or too short."""
    if not txt or not txt.strip():
        return None, 'empty'
    body = TS.sub('', txt)
    body = re.sub(r'\[[^\]]*\]', '', body)
    if PLACEHOLDER.search(body) and len(re.findall(r'[\u4e00-\u9fff]', body)) < 30:
        return None, 'placeholder'
    lines = [l for l in txt.splitlines() if TS.search(l) and TS.sub('', l).strip()]
    if len(lines) < 3:
        return None, 'too_short'
    return txt, 'ok'

def build_lrc(want, lyric, source, sid, score, conf, delta, src_note=''):
    """Build LRC with head and body.
    head: [ti:Title], [ar:Artist], [al:Album], [length:MM:SS]
    body: lyric lines
    re: source:ID, score=0.99, conf=high, dt=+0.1, src=note
    """
    head = [
        f"[ti:{want['title']}]",
        f"[ar:{'/'.join(want['artists'])}]",
        f"[al:{want.get('album', '')}]",
        f"[length:{mmss(want.get('duration'))}]",
    ]
    re_parts = [f're:{source}:{sid}', f'score={score}', f'conf={conf}']
    if delta is not None:
        re_parts.append(f'dt={delta:+.1f}')
    if src_note:
        re_parts.append(f'src={src_note}')
    head.append('[' + '|'.join(re_parts) + ']')
    body = '\n'.join(l for l in lyric.splitlines() if not META_LINE.match(l)).strip('\n')
    return '\n'.join(head) + '\n' + body + '\n'

# --------------------------------------------------------------------------
# 结果
# --------------------------------------------------------------------------
@dataclass
class LyricResult:
    """Single song result. status: ok | review | skip | failed"""
    path: str = ''
    lrc_path: Path | None = None
    status: str = 'failed'
    title: str = ''
    artist: str = ''
    album: str = ''
    dur: float = 0.0
    source: str = ''
    source_id: str = ''
    score: float | None = None
    conf: str = ''
    dur_delta: float | None = None
    note: str = ''
    cand: str = ''
    written: bool = False
    elapsed: float = 0.0
    # The three below are only passed within the process, not to log/JSON (lyric text too long)
    lyric: str = field(default='', repr=False)
    src_note: str = field(default='', repr=False)
    no_lyric: str = field(default='', repr=False)

    def as_dict(self):
        d = asdict(self)
        for k in ('lyric', 'src_note', 'no_lyric'):
            d.pop(k, None)
        return d

    def __str__(self):
        bits = [self.status, f'conf={self.conf or "-"}', f'score={self.score or "-"}']
        if self.dur_delta is not None:
            bits.append(f'dt={self.dur_delta:+.1f}')
        if self.source:
            bits.append(f'src={self.source}')
        if self.note:
            bits.append(f'note={self.note}')
        return ' '.join(bits)

@dataclass
class ServiceStats:
    queued: int = 0
    done: int = 0
    ok: int = 0
    review: int = 0
    skip: int = 0
    failed: int = 0
    written: int = 0
    dropped: int = 0

    def as_dict(self):
        return asdict(self)


# --------------------------------------------------------------------------
# Internal: cancel, rate limit
# --------------------------------------------------------------------------
class _Cancelled(BaseException):
    """stop() interrupted the wait. Inherited from BaseException to avoid being swallowed by single song's except Exception."""

class _RateLimiter:
    """Global rate limiter: at least interval seconds between any two requests; song mode: wait once per song.

    interval=0 when completely no wait (for local testing only). Wait in 1-second slices for stop() event,
    to ensure stop() won't get stuck in a 31-second sleep.
    """

    def __init__(self, interval, stop_event, logger):
        self.interval = max(float(interval or 0), 0.0)
        self.last = 0.0
        self.count = 0
        self.held = False
        self._stop = stop_event
        self._log = logger
        self._lock = threading.Lock()

    def wait(self):
        if self.interval <= 0 or self.held:
            return
        with self._lock:
            target = self.last + self.interval
            announced = False
            while True:
                gap = target - time.time()
                if gap <= 0:
                    break
                if self._stop.is_set():
                    raise _Cancelled()
                if not announced:
                    self._log.debug('限速等待 %.1fs', gap)
                    announced = True
                self._stop.wait(min(gap, 1.0))
            self.last = time.time()
            self.count += 1

    def hold(self):
        """song mode: wait once per song, then all requests within the song are let through."""
        self.held = False
        try:
            self.wait()
        finally:
            self.held = True

    def release(self):
        self.held = False

# --------------------------------------------------------------------------
# LyricService
# --------------------------------------------------------------------------
class LyricService:
    """Lyric service for watcher. Thread-safe: submit can be called from any thread."""

    def __init__(self, settings: Settings, http_getter=None, on_result=None):
        self.settings = settings
        self._get = http_getter # 注入 self._get 时走注入函数（自测用），签名 (url, timeout) -> (text, err)。
        # called in the worker thread with the finished LyricResult, must be cheap
        # and thread safe (the watcher posts it back to the event loop)
        self.on_result = on_result
        self._stop = threading.Event()
        self._queue = []
        self._queue_cv = threading.Condition()
        self._pending = set()
        self._worker = None
        self._local_lrcapi_ok = None
        self._local_netease_ok = None
        self._cooldown_n =0
        self._cooldowns = 0
        self.stats = ServiceStats()

        self.limiter = _RateLimiter(NETEASE_REQ_GAP, self._stop, logger)
        self._fb_limiter = _RateLimiter(FALLBACK_REQ_GAP, self._stop, logger)

    def start(self):
        # the lock keeps two concurrent submits from spawning two workers
        with self._queue_cv:
            if self._worker and self._worker.is_alive():
                return self
            self._stop.clear()
            self._worker = threading.Thread(target=self._loop, name='lyric-worker', daemon=True)
            self._worker.start()
        logger.info('Lyric service started.')
        return self

    def stop(self, timeout=10):
        self._stop.set()
        with self._queue_cv:
            self._queue_cv.notify_all()
        w = self._worker
        if w and w.is_alive():
            w.join(timeout)
            if w.is_alive():
                logger.warning('Lyric service did not stop within %ds', timeout)
        self._worker = None
        if self._queue:
            logger.warning('Lyric service queue is not empty. %d items were discarded.', len(self._queue))
        logger.info('Lyric service stopped | %s', self._fmt_stats())

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()

    # -------------- API ---------------------------
    def path_for(self, audio_path) -> Path:
        """Audio path → lrc path (same directory, same name, only change suffix).

        Accepts both an absolute path (watcher event) and a library relative path
        (Track.path in database), the lrc always lands next to the audio file.
        """
        p = Path(audio_path)
        if not p.is_absolute():
            p = self.settings.MUSIC_LIBRARY_PATH / p
        return p.with_suffix('.lrc')

    @staticmethod
    def _normalize_track(track: dict | None) -> dict | None:
        """Normalize the caller payload into the internal track shape.

        Keeps the contract to title/artists/album/duration (the fields the
        watcher parses from tags): artists may be a list or a 'A/B&C' string,
        duration may be missing (0.0).
        """
        if not track:
            return None
        raw_artists = track.get('artists')
        if isinstance(raw_artists, str):
            artists = split_artists(raw_artists)
        else:
            artists = [str(a).strip() for a in (raw_artists or []) if str(a).strip()]
        try:
            dur = float(track.get('duration') or 0)
        except (TypeError, ValueError):
            dur = 0.0
        return {
            'path': str(track.get('path') or ''),
            'title': (track.get('title') or '').strip(),
            'artists': artists,
            'album': (track.get('album') or '').strip(),
            'duration': dur,
        }

    def submit(self, track: dict):
        payload = self._normalize_track(track)
        if not payload:
            logger.debug('Empty track ignored.')
            return False
        if not payload['path']:
            logger.warning('Track without path ignored: %s', payload['title'] or '-')
            return False
        with self._queue_cv:
            if payload['path'] in self._pending:
                logger.debug('Track %s is already pending, ignored.', payload['path'])
                return False
            self._queue.append(payload)
            self._pending.add(payload['path'])
            self.stats.queued += 1
            self._queue_cv.notify()
        if not (self._worker and self._worker.is_alive()):
            self.start()
        return True

    def submit_many(self, tracks: list[dict]):
        n = sum(1 for t in tracks if self.submit(t))
        if n:
            logger.info('Submitted %d tracks.', n)
        return n

    def fetch(self, track):
        """Fetch a single lyric (CLI, fill, test). Do not call it directly from watcher's file callback."""
        track = self._normalize_track(track)
        if not track or not track['path']:
            return LyricResult(path=(track or {}).get('path', ''), status='failed', note='bad track')
        try:
            self.limiter.hold()
            try: 
                return self._fetch_one(track)
            finally:
                self.limiter.release()
        except _Cancelled:
            return LyricResult(path=track['path'], status='failed', note='cancelled')

    def fetch_many(self, tracks):
        return [self.fetch(t) for t in tracks]

    def stats_dict(self):
        return self.stats.as_dict()

    # -------------- Worker ---------------------------
    def _loop(self):
        logger.debug('Worker thread started.')
        while not self._stop.is_set():
            with self._queue_cv:
                # idle deadline, re-armed on every wait: as long as tracks keep
                # coming in the thread never exits, it only dies when it has been
                # doing nothing for IDLE_EXIT seconds.
                deadline = time.time() + IDLE_EXIT
                while not self._queue and not self._stop.is_set():
                    left = deadline - time.time()
                    if left <= 0:
                        # `_worker` is cleared under the same lock `submit` holds
                        # while appending, so a track queued right now is either
                        # seen here or forces submit() to start a new thread.
                        self._worker = None
                        logger.info('Lyric worker idle for %ss, thread exited.', IDLE_EXIT)
                        return
                    self._queue_cv.wait(left)   # woken by submit()/stop(), no polling
                if self._stop.is_set():
                    break
                t = self._queue.pop(0)
            try:
                self.limiter.hold()
                try:
                    res = self._fetch_one(t)
                finally:
                    self.limiter.release()
            except _Cancelled:
                with self._queue_cv:
                    self._pending.discard(t['path'])
                logger.info('Track %s cancelled.', t['path'])
                break
            except Exception:
                logger.exception('Lyric fetch failed: %s', t['path'])
                res = LyricResult(path=t['path'], status='failed', note='exception')
            with self._queue_cv:
                self._pending.discard(t['path'])
            self._account(res)
            self._emit(res)
        logger.debug('Worker thread stopped.')

    def _emit(self, res: LyricResult):
        '''hand a finished result to the caller callback (db writer, cli hook...)'''
        if not self.on_result:
            return
        try:
            self.on_result(res)
        except Exception:
            logger.exception('Lyric callback failed: %s', res.path)

    def _account(self, res):
        self.stats.done += 1
        if res.status in ('ok', 'review', 'skip', 'failed'):
            setattr(self.stats, res.status, getattr(self.stats, res.status) + 1)
        if res.written:
            self.stats.written += 1
        if self.stats.done % 20 == 0:
            logger.info('Progress: %s', self._fmt_stats())

    def _fmt_stats(self):
        s = self.stats
        return (f'Queued: {s.queued}, Done: {s.done} (ok {s.ok} | review {s.review} | skip {s.skip} | failed {s.failed}), Written: {s.written} | Dropped: {s.dropped}')

    # -------------- Fetch ---------------------------
    def _fetch_one(self, track: dict):
        t0 = time.time()
        res = LyricResult(
            path=track['path'],
            lrc_path=self.path_for(track['path']),
            title=clean_title(track['title']),
            artist='/'.join(track['artists'] or []),
            album=track['album'] or '',
            dur=round(float(track['duration'] or 0), 3)
        )
        try:
            self._run(track, res)
        except _Cancelled:
            raise
        except Exception as e:
            res.status, res.note = 'failed', f'exc:{type(e).__name__}:{e}'[:200]
            logger.exception('Fetch failed: %s', track['path'])
        res.elapsed = round(time.time() - t0, 1)
        self._log_result(res)
        return res

    def _run(self, track, res: LyricResult, overwrite = False):
        if not track['title']:
            res.status, res.note = 'skip', 'no_title'
            return
        
        if res.lrc_path and res.lrc_path.exists() and not overwrite:
            if not self._stale(str(res.lrc_path), track['title']):
                # a lyric file is ready on disk: this is a success, not a skip.
                # 'skip' is reserved for tracks that cannot be fetched at all.
                res.status, res.note, res.written = 'ok', 'exists', True
                return
            logger.info('Existed lyric is stale with title, will be overwritten: %s', res.lrc_path)
        
        primary = self._primary(track, res, overwrite)
        if primary =='fallback':
            why = res.note or 'primary_failed'
            fb = self._run_fallback(track, res)
            if fb is None:
                if res.no_lyric:
                    res.status, res.note = 'skip', f'nolyric_{res.no_lyric}'
                else:
                    res.status = 'failed'
                    res.note = f'{why}|fb_none'
                return
            res.__dict__.update(fb)
            res.note = (res.note + '|' if res.note else '') + f'primary:{why}'
        self._maybe_write(track, res)


    # ----------------- Main Source --------------------------------
    def _build_query(self, track):
        arts = [a for a in track['artists'] if norm_key(a) not in UNKNOWN_ARTIST]
        return f'{track['title']} {arts[0]}' if arts else track['title']

    def _fail_search(self, res: LyricResult, err):
        """搜索层失败的分流：接口故障（含 405）不触发兜底，那是接口的事。"""
        res.source = 'netease'
        if err == 'code405':
            res.status, res.note = 'failed', 'code405'
            return 'done'
        res.status, res.note = 'failed', f'net:{err}'
        return 'done' if _is_net_error(err) else 'fallback'

    def _search(self, query, offset=0):
        d, err = self._http(self.settings.LC_NETEASE_API + '/cloudsearch?' + urlencode(
            {'keywords': query, 'type': 1, 'limit': PAGE_CANDIDATES_COUNT, 'offset': offset}
        ))
        songs = ((d or {}).get('result') or {}).get('songs') or []
        if not songs and not err:
            d, err = self._http(self.settings.LC_NETEASE_API + '/search?' + urlencode(
            {'keywords': query, 'type': 1, 'limit': PAGE_CANDIDATES_COUNT, 'offset': offset}
            ))
            songs  = ((d or {}).get('result') or {}).get('songs') or []
        return parse_candidates(songs), err, len(songs)

    def _primary(self, track, res: LyricResult, overwrite=False):
        ''' Can try fallback if return 'fallback', otherwise, result written in res'''
        query = self._build_query(track)
        pool, err, raw = self._search(query)
        if err and not pool:
            return self._fail_search(res, err)
        if not pool and query != track['title']:
            pool, err, raw = self._search(track['title'])
            query = track['title']
            if err and not pool:
                return self._fail_search(res, err)
        if not pool:
            res.status, res.note, res.source = 'failed', 'no_candidate', 'netease'
            return 'fallback'

        scored = self._rank(pool, track)
        page = 1
        while page < PAGES and raw >= PAGE_CANDIDATES_COUNT and (not scored or scored[0][1] != 'low'):
            logger.debug('第一页最佳 conf=%s, 翻到第 %s 页', 
                scored[0][1] if scored else 'none', page + 1)
            more, e2, raw2 = self._search(query, offset=page * PAGE_CANDIDATES_COUNT)
            if not more:
                break
            page += 1
            raw = raw2
            pool.extend(more)
            scored = self._rank(pool, track)
        
        if not scored:
            res.status, res.note, res.source = 'failed', 'all_rejected', 'netease'
            res.cand = self._top_note(pool[:3])
            return 'fallback'

        s, conf, det, c = scored[0]
        res.source, res.source_id = 'netease', str(c['id'])
        res.score, res.conf, res.dur_delta = s, conf, det['dt']
        res.cand = self._top_note([x[3] for x in scored[:3]])
        res.src_note = f'{c['title']} / {'/'.join(c['artists'])} / {c['album']}'[:120]

        if conf == 'low':
            # 曲名歌手都对、只差版本时长 —— 标出来方便人工一眼判
            res.status = 'review'
            res.note = 'dur_diff' if (det['tsim'] >= 0.95 and det['asc'] == 1.0
                                    and det['dt'] is not None and abs(det['dt']) <= 10) else 'low'
            if overwrite:
                res.lyric = self._lyric_text(c['id'])
            return 'done'

        lyric, lerr = self._lyric(c['id'])
        if lerr and not lyric:
            res.status, res.note = 'failed', f'lyric_net:{lerr}'
            return 'done'
        txt, why = validate_lyric(lyric)
        if not txt:
            if why == 'placeholder':
                # 「纯音乐，请欣赏」：本来就没有词，别记成失败
                res.status, res.note = 'skip', 'instrumental'
                return 'done'
            res.status, res.note = 'failed', f'lyric_{why}'
            res.no_lyric = why
            return 'fallback'
        res.status = 'ok'
        res.lyric = txt
        if det.get('lenient'):
            res.note = 'dur_lenient'
        return 'done'

    def _lyric(self, song_id):
        d, err = self._http(self.settings.LC_NETEASE_API + '/lyric?' + urlencode({'id': song_id}))
        if not d:
            return '', err or 'empty'
        return ((d.get('lrc') or {}).get('lyric') or ''), ''

    def _lyric_text(self, song_id):
        """review 也把候选歌词取回来放进结果（写不写由上层决定）。"""
        txt, _ = self._lyric(song_id)
        return validate_lyric(txt)[0] or ''
    
    def _rank(self, pool, track):
        scored = []
        for c in pool:
            if c.get('status') == 0:
                continue
            r = score_candidate(c, track, LENIENT_DURATION)
            if r:
                scored.append((r[0], r[1], r[2], c))
        scored.sort(key=lambda x: -x[0])
        return scored

    def _top_note(self, cands):
        """前几个候选写进日志，便于事后对账；同一录音的重复条目只留一条。"""
        parts, seen = [], set()
        for c in cands:
            key = (norm_key(c['title']), tuple(norm_key(a) for a in c['artists']),
                   round(c['duration'] or 0))
            if key in seen:
                continue
            seen.add(key)
            parts.append(f"{c['title']}·{'/'.join(c['artists'])}·{mmss(c['duration'])}#{c['id']}")
            if len(parts) >= 3:
                break
        return ' ; '.join(parts)

    def _log_result(self, res: LyricResult):
        line = '%s  %s  <- %s' % (res.status.upper(), res.path, res)
        if res.written and res.lrc_path:
            line += f'  -> {res.lrc_path}'
        if res.cand:
            line += f'  | {res.cand}'
        if res.status in ('ok', 'review'):
            logger.info(line)
        elif res.status == 'skip':
            logger.info(line)
        else:
            logger.warning(line)

    # ------------------ Fallback Source ----------------------------------
    def _run_fallback(self, track, res):
        for func in [self._from_lrclib, self._from_lrcapi]:
            if self._stop.is_set():
                raise _Cancelled
            try:
                r = func(track)
            except _Cancelled:
                raise
            except Exception:
                logger.exception('Fallback %s error', func.__name__)
                continue
            if r:
                return r
        return None

    def _from_lrclib(self, track):
        arts = [a for a in track['artists'] if norm_key(a) not in UNKNOWN_ARTIST]
        if not arts or not track['duration']:
            return None
        q = {'artist_name': arts[0], 'track_name': track['title'], 'duration': int(round(track['duration']))}
        tries = [dict(q, album_name=track['album'])] if track['album'] else []
        tries.append(q)
        for kw in tries:
            d, err = self._http(self.settings.LRCLIB_API + '/get?' + urlencode(kw), timeout=NET_TIMEOUT, rl=self._fb_limiter)
            if err:
                logger.debug('lrclib net error: %s', err)
                return None
            if not d:
                continue
            if d.get('instrumental'):
                return {'status': 'skip', 'note': 'instrumental', 'source': 'lrclib', 'written': False, 'conf': 'high'}
            lyr =(d.get('syncedLyrics') or '').strip()
            if not lyr:
                continue
            txt, why = validate_lyric(lyr)
            if not txt:
                continue
            cand = {
                'id': f'lrclib:{d.get('id')}', 'title': d.get('trackName') or track['title'],
                'artists': [d.get('artistName') or ''], 'album': d.get('albumName') or '',
                'duration': float(d.get('duration') or 0), 'status': 1, 'cover': False,
                'lyric': lyr, 'has_total': True
            }
            return self._judge_fallback(cand, track, 'lrclib')
        return None

    def _from_lrcapi(self, track):
        arts = [a for a in track['artists'] if norm_key(a) not in UNKNOWN_ARTIST]
        if not arts:
            return None
        if not self._local_lrcapi_alive():
            return None
        q = {'title': track['title'], 'artist': arts[0]}
        if track['duration']:
            q['duration'] = int(round(track['duration']))
        d, err = self._http(self.settings.LC_LRCAPI + '/jsonapi?' + urlencode(q), timeout=NET_TIMEOUT, retries=1, rl=self._fb_limiter)
        if err or not isinstance(d, list):
            return None
        best = None
        for it in d:
            ly = it.get('lyrics') or ''
            if not ly.strip():
                continue
            head = parse_lrc_head(ly)
            cand = {
                'id': 'lrcapi:' + str(it.get('id') or ''),
                'title': head.get('title') or it.get('title') or '',
                'artists': split_artists(it.get('artist') or '') or [head.get('artist') or ''],
                'album': it.get('album') or head.get('album') or '',
                'duration': head['dur'], 'status': 1, 'cover': False,
                'lyric': ly, 'has_total': bool(head['dur']),
            }
            r = self._judge_fallback(cand, track, 'lrcapi')
            if r and (best is None or r['score'] > best['score']):
                best = r
        return best

    def _judge_fallback(self, cand, want, source):
        """兜底比主源更严：曲名歌手双精确 + 有时长时偏差 ≤3s。

        纯音乐的假命中全是「同名不同歌手」，靠 asc==1.0 整批挡下。
        """
        r = score_candidate(cand, want, LENIENT_DURATION)
        if not r:
            return None
        s, conf, det = r
        if det['asc'] < 0.999 or det['tsim'] < 0.9:
            return None
        if cand.get('has_total') and det['dt'] is not None and abs(det['dt']) > 3:
            return None
        txt, why = validate_lyric(cand['lyric'])
        if not txt:
            return None
        solid = bool(cand.get('has_total')) and det['tsim'] >= 0.95 and det['asc'] == 1.0
        src_note = f"{cand['title']} / {'/'.join(cand['artists'])} / {cand['album']}"
        return {
            'status': 'ok' if solid else 'review',
            'source': source, 'source_id': str(cand['id']),
            'score': s, 'conf': conf, 'dur_delta': det['dt'],
            'lyric': txt, 'cand': self._top_note([cand]),
            'src_note': src_note.replace('|', '¦')[:120],
            'note': '' if solid else f'fb_{source}_no_dur',
            'written': False,
        }

    def _local_netease_alive(self):
        if self._local_netease_ok is None:
            self._local_netease_ok = _port_open(self.settings.LC_NETEASE_API)
            if not self._local_netease_ok:
                logger.warning('Local netease api service is not open: %s', self.settings.LC_NETEASE_API)
        return self._local_netease_ok

    def _local_lrcapi_alive(self):
        if self._local_lrcapi_ok is None:
            self._local_lrcapi_ok = _port_open(self.settings.LC_LRCAPI)
            if not self._local_lrcapi_ok:
                logger.warning('Local lrcapi service is not open: %s', self.settings.LC_LRCAPI)
        return self._local_lrcapi_ok

    # -------------------- write lyric ----------------------------
    def _maybe_write(self, track, res: LyricResult):
        if res.status not in ('ok', 'review'):
            return
        allow = res.status == 'ok' or (res.status == 'review' and WRITE_REVIEW)
        if not allow:
            res.note = (res.note + '|' if res.note else '') + 'not_written_review'
            logger.debug('low confidence and not written: %s %s', str(res.lrc_path), res)
            return
        if not res.lyric:
            res.note = (res.note + '|' if res.note else '') + 'no_lyric'
            return
        txt = build_lrc(track, res.lyric, res.source or '', res.source_id or '',
                res.score if res.score is not None else '-',
                res.conf or '-', res.dur_delta, res.src_note)
        if not res.lrc_path:
            res.lrc_path = self.path_for(track['path'])
        tmp = res.lrc_path.with_suffix('.tmp')
        try:
            res.lrc_path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, 'w', encoding='utf-8') as fh:
                fh.write(txt)
            tmp.replace(res.lrc_path)
            res.written = True
            if res.status == 'review':
                res.note = (res.note + '|' if res.note else '') + 'written_review'
            logger.info('LRC written: %s (src=%s, conf=%s, score=%s)',
                        res.lrc_path, res.source or '-', res.conf or '-',
                        res.score if res.score is not None else '-')
        except OSError as e:
            res.note = (res.note + '|' if res.note else '') + f'write:{e}'
            res.status = 'failed'
            logger.error('Write error %s: %s', res.lrc_path, e)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass


    def _stale(self, lrc_path, title):
        """已有 lrc 的 [ti:] 与这次曲名对不上 → 视为过期，可覆盖。"""
        try:
            with open(lrc_path, encoding='utf-8', errors='replace') as fh:
                head = fh.read(2000)
        except OSError:
            return False
        m = re.search(r'^\[ti:(.*?)\]\s*$', head, re.M)
        if not m:
            return True
        return sim(m.group(1).strip(), title) < 0.85
    
    def _http(self, url, timeout=None, retries=2, rl: _RateLimiter | str ='default'):
        """返回 (data, err)。err 非空＝网络层失败，区别于「查到了但没有结果」。

        code=405 藏在 HTTP 200 的 body 里：必须在解析后拦，否则会被当成「没这首歌」
        记成 failed。命中后全流水线冷却（服务里就是 worker 停摆一段时间）。
        """
        limiter = self.limiter if rl == 'default' else rl
        main = rl == 'default'
        if self._stop.is_set():
            raise _Cancelled()
        timeout = timeout or NET_TIMEOUT
        err = ''
        i = 0
        cool = 0
        while i <= retries:
            if limiter and isinstance(limiter, _RateLimiter):
                limiter.wait()
            raw, terr = self._fetch_raw(url, timeout)
            if terr == '404':
                return None, ''
            if terr:
                err = terr
            else:
                try:
                    data = json.loads(raw or '')
                except ValueError as e:
                    err = f'json:{e}'
                else:
                    if main and _is_limited(data, NETEASE_LIMIT_CODE):
                        cool += 1
                        if cool > COOL_DOWN_MAX:
                            logger.error('连续冷却 %s 次后仍是 code=405，放弃本次请求（%s）',
                                           COOL_DOWN_MAX, urlparse(url).path)
                            return None, 'code405'
                        self._cooldown_405(urlparse(url).path, cool)
                        continue
                    return data, ''
            i += 1
            if i <= retries:
                tag = ('netease' if url.startswith(self.settings.LC_NETEASE_API)
                       else 'lrclib' if 'lrclib' in url or url.startswith(self.settings.LRCLIB_API)
                       else 'lrcapi' if '/jsonapi' in url or url.startswith(self.settings.LC_LRCAPI)
                       else urlparse(url).netloc)
                logger.debug('请求失败(%s｜%s)，%ss 后重试', err, tag, 3 * i)
                if self._stop.wait(3 * i):
                    raise _Cancelled()
        return None, err
    
    def _fetch_raw(self, url, timeout) -> tuple[str | None, str]:
        """取原始响应体，返回 (text, err)。err='404' 单独标出来（表示「真没有」）。

        注入 self._get 时走注入函数（自测用），签名 (url, timeout) -> (text, err)。
        """
        if self._get:
            return self._get(url, timeout)
        try:
            req = Request(url, headers={'User-Agent': UA})
            with urlopen(req, timeout=timeout) as r:
                return r.read().decode('utf-8', 'replace'), ''
        except HTTPError as e:
            return None, '404' if e.code == 404 else f'http{e.code}'
        except (URLError, socket.timeout, TimeoutError) as e:
            return None, f'net:{getattr(e, "reason", e)}'
        except Exception as e:
            return None, f'{type(e).__name__}:{e}'

    def _cooldown_405(self, path, n):
        self._cooldown_n = n
        self._cooldowns += 1
        resume = datetime.fromtimestamp(time.time() + COOL_DOWN)
        logger.warning('主源限流 code=405（%s），全局冷却至 %s，本轮第 %s/%s 次',
                         path, resume.strftime('%H:%M'), n, COOL_DOWN_MAX)
        end = time.time() + COOL_DOWN
        nxt = time.time() + 300
        while True:
            left = end - time.time()
            if left <= 0:
                return
            if self._stop.is_set():
                raise _Cancelled()
            if time.time() >= nxt:
                logger.warning('限流冷却中，剩余 %.0f 分钟', left / 60)
                nxt = time.time() + 300
            self._stop.wait(min(left, 1.0))


# ------------- utils -------------------
def _is_limited(d, code=405):
    if not isinstance(d, dict):
        return False
    c = d.get('code')
    if c is None:
        return False
    try:
        return int(c) == int(code)
    except (TypeError, ValueError):
        return str(c).strip() == str(code)

def _is_net_error(err):
    """网络层错误（重试后仍失败）才算接口故障；code405 也算接口侧问题。"""
    return bool(err) and (str(err).startswith('net:') or str(err).startswith('http5')
                          or 'code405' in str(err) or str(err).startswith('timeout')
                          or str(err).startswith('socket'))

def _port_open(url):
    try:
        u = urlparse(url)
        host = str(u.hostname) if u.hostname else None
        if not host:
            return False
        port = u.port or 80
        s = socket.create_connection((host, port), timeout=1.0)
        s.close()
        return True
    except Exception:
        return False