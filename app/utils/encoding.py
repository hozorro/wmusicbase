from __future__ import annotations

import difflib
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable, Sequence
from weakref import ref

__all__ = [
    'LEGACY_CANDIDATES',
    'RecoveredText',
    'recover_legacy_text',
    'detect_shared_encoding',
    'to_bytes',
    'score_candidates'
]

# --------------------------------------------------------------------------
# candidate codecs
# --------------------------------------------------------------------------
# Order carries meaning: it is the tie-break order, and it is deliberately
# ordered by "what a Chinese music library most plausibly contains".
# utf-8 first because plenty of modern tags are mislabelled UTF-8;
# gb18030 before big5 so that mainland files keep their historical result
# whenever the scores are indistinguishable.
LEGACY_CANDIDATES: tuple[str, ...] = (
    'utf-8',
    'gb18030',
    'cp950',
    'big5',
    'shift_jis',
    'euc-kr',
    'cp1252'
)

def _gb2312_level1() -> frozenset[str]:
    """GB2312 level-1 hanzi (rows 0xB0-0xD7) -- the PRC 'commonly used' set."""
    chars: list[str] = []
    for row in range(0xB0, 0xD8):
        for cell in range(0xA1, 0xFF):
            try:
                chars.append(bytes((row, cell)).decode('gb2312'))
            except UnicodeDecodeError:
                continue
    return frozenset(chars)

def _big5_common() -> frozenset[str]:
    """Big5 commonly-used block (0xA440-0xC67E) -- the PRC-Taiwan 'commonly used' set."""
    chars: list[str] = []
    for row in range(0xA4, 0xC7):
        for cell in range(0x40, 0x7F):
            try:
                chars.append(bytes((row, cell)).decode('big5'))
            except UnicodeDecodeError:
                continue
        for cell in range(0xA1, 0xFF):
            try:
                chars.append(bytes((row, cell)).decode('big5'))
            except UnicodeDecodeError:
                continue
    return frozenset(chars)

# Union of both national "common" sets.  A correct Chinese / Japanese decode
# lands inside this set; wrong-codec debris lands outside it.
_COMMON_HAN: frozenset[str] =  _gb2312_level1() | _big5_common()

# Traditional-only forms that the two tables above miss but that show up all
# over real-world track metadata.  Kept small and explicit on purpose.
_EXTRA_COMMON: frozenset[str] = frozenset(
    '傑倫綠聽嗎麼機藥臺灣網頁麵線麵'
    '邨峯峯強彊聲樹針對據'
)

_COMMON: frozenset[str] = _COMMON_HAN | _EXTRA_COMMON

# Characters that are unambiguous evidence of a *wrong* decode.
def _is_pua(ch: str) -> bool:
    return 0xE000 <= ord(ch) <= 0xF8FF or 0xF0000 <= ord(ch) <= 0x10FFFD

# --------------------------------------------------------------------------
# scoring
# --------------------------------------------------------------------------
def _script_profile(text: str) -> dict[str, int]:
    """
    Count characters by unicode script family relevant to CJK guesswork.

    The buckets are mutually exclusive, so ``sum(...values())`` is exactly
    ``len(text)``.  (An earlier version incremented two buckets at once and
    silently halved every Chinese score, letting Hangul win by accident --
    if you change this function, keep that invariant.)
    """
    p = dict(
        ascii=0, han_common=0, han_rare=0, han_ext=0, kana=0, hangul=0,
        pua=0, punct=0, compat=0, junk=0, control=0
    )
    for ch in text:
        cp = ord(ch)
        if cp < 0x80:
            p['ascii'] += 1
        elif _is_pua(ch):
            p['pua'] += 1
        elif ch in _COMMON:
            p['han_common'] += 1
        elif 0x3400 <= cp <= 0x4DBF:          # CJK ext A -- almost always noise
            p['han_ext'] += 1
        elif 0x4E00 <= cp <= 0x9FFF or 0xF900 <= cp <= 0xFAFF:
            p['han_rare'] += 1
        elif 0x3040 <= cp <= 0x30FF or 0x31F0 <= cp <= 0x31FF:
            p['kana'] += 1
        elif 0xAC00 <= cp <= 0xD7AF or 0x3130 <= cp <= 0x318F \
                or 0x30FB <= cp <= 0x30FF:
            p['hangul'] += 1
        elif 0x3000 <= cp <= 0x303F:
            p['punct'] += 1
        elif 0xFF00 <= cp <= 0xFFEF:
            p['compat'] += 1
        elif unicodedata.category(ch)[0] == 'C':
            p['control'] += 1
        else:
            p['junk'] += 1
    return p

def _heuristic_score(text: str) -> float:
    """
    Score one decoded candidate on how much it looks like real text.

    Han characters that appear in the standard common tables are the main
    positive signal; everything a broken decode produces is negative.
    """
    p = _script_profile(text)
    total = sum(p.values())
    if not total:
        return 0.0
    
    score = 0.0
    score += 1.0 * p['han_common']          # the payoff
    score += 0.8 * p['hangul']              # a clean hangul run is real evidence
    score += 0.3 * p['kana']                # likewise a clean kana run
    score -= 0.8 * p['han_rare']            # plausible-ish, but suspicious
    score -= 1.2 * p['han_ext']             # almost never intentional in tags
    score -= 4.0 * p['pua']                 # dead giveaway of a bad decode
    score -= 0.5 * p['compat']              # half-width katakana soup
    score -= 0.4 * p['junk']
    score -= 6.0 * p['control']

    # Hangul sharing a tag with kana or han means several codecs are fighting
    # over the same bytes and all of them are wrong.  Kanji + kana on its own
    # is NOT suspicious -- that is simply how Japanese is written.
    han = p['han_common'] + p['han_rare'] + p['han_ext']
    if p['hangul'] > 0 and (p['kana'] > 0 or han > 0):
        score -= 5.0

    # Normalise by character count (the buckets are exclusive, so this is
    # len(text)): long fields must not outvote short ones when we pick one
    # codec for a whole file.
    return score / total * 10.0

def _similarity(text: str, reference: str) -> float:
    if not text or not reference:
        return 0.0
    return SequenceMatcher(None, text, reference).ratio()


# --------------------------------------------------------------------------
# Western-text gate
# --------------------------------------------------------------------------
# Before we start guessing between Chinese codecs we must make sure we are not
# looking at "Björk" or "Große Freiheit".  A single stray high byte can be
# swallowed into a plausible-looking CJK pair and score higher than the correct
# Latin reading, so this has to be decided on the *shape* of the bytes rather
# than left to the scorer.

_WESTERN_BLOCKS = (
    (0x00A0, 0x024F),   # Latin-1 Supplement + Latin Extended A/B
    (0x0250, 0x02FF),   # IPA / spacing modifiers
    (0x0370, 0x03FF),   # Greek
    (0x0400, 0x04FF),   # Cyrillic
    (0x1E00, 0x1EFF),   # Latin Extended Additional
)

# Non-ASCII density above which a string stops looking like accented Latin prose
# and starts looking like multibyte CJK.  25% is comfortable: even 'Ñoño' is
# 50%, while a mangled UTF-8 'BjÃ¶rk' is ~29% and correctly keeps going.
_WESTERN_DENSITY_LIMIT = 0.25

def _is_western_char(ch: str) -> bool:
    cp = ord(ch)
    if cp < 0x80:
        return True
    if unicodedata.category(ch)[0] =='C':
        return False
    return any(lo <= cp <= hi for lo, hi in _WESTERN_BLOCKS)

def _pick_western(raw: bytes) -> tuple[str, str] | None:
    """
    Return (codec, text) when the bytes are plainly Western Latin text.

    Checks the three plausible single-byte/UTF-8 readings and keeps the one
    with the sparsest non-ASCII characters: genuine accented Latin leaves them
    isolated, while a UTF-8 payload misread as cp1252 leaves a dense smear
    ('BjÃ¶rk'), so lowest density wins the comparison honestly.
    """
    best: tuple[str, str] | None = None
    best_density: float | None = None

    for codec in ('utf-8', 'cp1252', 'latin1'):
        try:
            text = raw.decode(codec)
        except (UnicodeDecodeError, LookupError):
            continue
        non_ascii = [ch for ch in text if ord(ch) >= 0x80]
        if not non_ascii:
            return codec, text
        density = len(non_ascii) / len(text)
        if density > _WESTERN_DENSITY_LIMIT:
            continue
        if not all(_is_western_char(ch) for ch in non_ascii):
            continue
        if best_density is None or density < best_density:
            best, best_density = (codec, text), density
    return best

def _looks_western(text: str, limit: float = _WESTERN_DENSITY_LIMIT) -> bool:
    """True when every non-ASCII char is Latin/Greek/Cyrillic and they are sparse."""
    if not text:
        return True
    non_ascii = [ch for ch in text if ord(ch) >= 0x80]
    if not non_ascii:
        return True
    if len(non_ascii) / len(text) > limit:
        return False
    return all(_is_western_char(ch) for ch in non_ascii)


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
@dataclass
class RecoveredText:
    """Result of one legacy-decoding attempt."""
    text: str
    encoding: str
    confidence: str          # 'declared' | 'ascii' | 'reference' | 'heuristic' | 'failed'
    score: float = 0.0
    candidates: dict[str, float] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.text)

def to_bytes(raw_value, declared_encoding: str = 'latin1') -> bytes:
    """
    Normalise whatever mutagen handed us into the original bytes.

    mutagen gives either ``bytes`` (modern) or an already-latin1-decoded
    ``str`` (older / v1-synthesised frames).  latin1 round-trips byte for
    byte, so no information is lost either way.
    """
    if isinstance(raw_value, (bytes, bytearray, memoryview)):
        return bytes(raw_value)
    if isinstance(raw_value, str):
        try:
            return raw_value.encode(declared_encoding, errors='ignore')
        except LookupError:
            return raw_value.encode('utf-8', errors='ignore')
    if raw_value is None:
        return b''
    return str(raw_value).encode('utf-8', errors='ignore')


def candidate_results(raw: bytes, candidates: Sequence[str] = LEGACY_CANDIDATES) -> list[tuple[str, str, float]]:
    """Decode ``raw`` with every candidate. Skips ones that fail strictly."""
    out: list[tuple[str, str, float]] = []
    for enc in candidates:
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        out.append((enc, text, _heuristic_score(text)))
    return out

def score_candidates(
    raw: bytes, 
    candidates: Sequence[str] = LEGACY_CANDIDATES,
    reference: str | None = None,
) -> list[tuple[str, str, float, float]]:
    """Public view of every option considered -- useful when tuning or logging."""
    rows = []
    for enc, text, base in candidate_results(raw, candidates):
        rows.append((enc, text, base, _similarity(text, reference or '')))
    return rows

def detect_shared_encoding(raws: Iterable[bytes | str], candidates: Sequence[str] = LEGACY_CANDIDATES) -> str | None:
    """
    Pick ONE codec for a whole file rather than per field.

    A single 3-character artist field is weak evidence; six fields that all
    agree are much stronger.  Summing the per-field scores rewards codecs that
    stay linguistically coherent across the whole tag block, which is exactly
    what a real codec does and what a wrong one cannot sustain.

    Returns None when the input has nothing worth guessing about.
    """
    totals: dict[str, float] = {enc: 0.0 for enc in candidates}
    hits: dict[str, int] = {enc: 0 for enc in candidates}
    considered = 0

    for raw in raws:
        raw = to_bytes(raw)
        if not raw or raw.isascii():
            continue
        considered += 1
        for enc, _text, score in candidate_results(raw, candidates):
            totals[enc] += score
            hits[enc] += 1

    if not considered:
        return None

    order = {enc: i for i, enc in enumerate(candidates)}
    # Require a candidate to have survived every field that yielded anything;
    # a codec that fails mid-way through the file cannot be the right one.
    viable = [enc for enc in candidates if hits[enc] == considered]
    if not viable:
        viable = [enc for enc in candidates if hits[enc] > 0]
    if not viable:
        return None
    return max(viable, key=lambda enc: (totals[enc], -order[enc]))
    
def recover_legacy_text(
    raw: bytes | str,
    reference: str | None = None,
    candidates: Sequence[str] = LEGACY_CANDIDATES,
    forced: str | None = None,
) -> RecoveredText:
    """
    Recover text whose declared encoding is ISO-8859-1 (or unknown).

    ``reference`` is a trustworthy sibling value for the same logical field
    (typically the UTF-8 string from an APEv2 tag in the same file).  Supplying
    it promotes the decision from a statistical guess to a direct match, and
    is the single most effective way to disambiguate GB18030 vs Big5.

    ``forced`` short-circuits detection with an already-decided codec -- used
    after :func:`detect_shared_encoding` has voted on the file as a whole, so
    every field inside one file is decoded consistently.

    Never raises; on total failure it degrades to latin1 with errors ignored.
    """
    raw = to_bytes(raw)
    if not raw:
        return RecoveredText('', 'empty', 'failed')

    # Fast path: nothing above ASCII means nothing to guess about.
    if raw.isascii():
        return RecoveredText(
            raw.decode('ascii').replace('\x00', '').strip(),
            'ascii',
            'ascii',
            score=0.0,
        )
    
    if forced:
        try:
            text = raw.decode(forced)
            # A whole-file vote must not bulldoze through obviously Western text.
            if not _looks_western(text, limit=1.0) or _looks_western(text):
                return RecoveredText(text.strip(), forced, 'voted', 0.0)
        except (UnicodeDecodeError, LookupError):
            pass    # fall through to detection

    # Western gate: real Latin text must never reach the CJK scorer, which
    # would happily chew "Große Freiheit" into a made-up ideograph.
    western = _pick_western(raw)
    if western:
        codec, text = western
        return RecoveredText(
            text.strip(), codec, 'western', 0.0,
            {codec: _heuristic_score(text)}
        )

    scored = candidate_results(raw, candidates)
    if not scored:
        return RecoveredText(
            raw.decode('latin1', errors='ignore').strip(),
            'latin1',
            'failed',
        )
    
    order = {enc: i for i, enc in enumerate(candidates)}

    if reference:
        # Verify against ground truth when we have it, but keep the heuristic
        # as a secondary key so we do not flip to a nonsense codec just
        # because SequenceMatcher found a spurious 0.01 improvement.
        ranked = sorted(
            scored,
            key=lambda r: (-_similarity(r[1], reference), -r[2], order[r[0]])
        )
        best_enc, best_text, best_base = ranked[0]
        sim = _similarity(best_text, reference)
        runner_up = _similarity(ranked[1][1], reference) if len(ranked) > 1 else 0.0
        # Only call it verified when one candidate clearly beats the others.
        decided = sim >= 0.6 and sim - runner_up >= 0.15
        confidence = 'reference' if decided else 'heuristic'
        return RecoveredText(
            best_text.strip(), best_enc, confidence, best_base,
            {enc: score for enc, _, score in scored}
        )
    
    ranked = sorted(scored, key=lambda r: (-r[2], order[r[0]]))
    best_enc, best_text, best_base = ranked[0]
    return RecoveredText(
        best_text.strip(), best_enc, 'heuristic', best_base,
        {enc: score for enc, _, score in scored}
    )
