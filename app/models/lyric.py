# -*- encoding: utf-8 -*-
'''
@File      :   lyric.py
@Time      :   2025/11/01 10:00:00
@Author    :   enauvy
@Version   :   1.0
@Copyright :   ©2018-2025 WEYECO <enauvy@qq.com>
@Desc      :   lyric model, one row per track (1:1), lyric file index and full text search
'''


from typing import TYPE_CHECKING, Optional
if TYPE_CHECKING:
    from . import Track

from datetime import datetime
from sqlalchemy import ForeignKey, String, Text, Index, CheckConstraint, Boolean
from sqlalchemy.dialects.postgresql import TIMESTAMP, TSVECTOR
from sqlalchemy.orm import relationship, Mapped, mapped_column
from . import Base, DateTimeMixin

# lyric fetch states:
#   pending: no lyric file yet, waiting for the fetcher
#   ok     : lyric file exists and is usable
#   review : fetched but low confidence, written only when WRITE_REVIEW is on
#   skip   : not fetchable at all (instrumental, no title, empty/invalid content)
#   failed : network/api error, retryable
LYRIC_STATUS = ('pending', 'ok', 'review', 'skip', 'failed')
# best line extraction states:
#   pending  : waiting for the external extractor
#   extracted: best line present
#   skip     : terminal, nothing to extract (no lyric) or extraction failed
BEST_STATUS = ('pending', 'extracted', 'skip')


class Lyric(Base, DateTimeMixin):
    __tablename__ = 'lyrics'

    id: Mapped[int] = mapped_column(primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey('tracks.id', ondelete='CASCADE'), unique=True)
    # same format as tracks.path, only the suffix changes to .lrc
    path: Mapped[str] = mapped_column(String(), unique=True)

    # fetch result, mirrors LyricResult of app/services/lyric_service.py
    status: Mapped[str] = mapped_column(String(16), default='pending', server_default='pending')
    score: Mapped[float | None]
    dur_delta: Mapped[float | None]
    source: Mapped[str | None] = mapped_column(String(32))
    source_id: Mapped[str | None] = mapped_column(String(64))
    fetch_note: Mapped[str | None] = mapped_column(Text)

    # disk fact, independent of the fetch result
    written: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')
    written_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    # searchable content (only filled when written is true)
    lyric_plain: Mapped[str | None] = mapped_column(Text)
    lyric_tsv: Mapped[str | None] = mapped_column(TSVECTOR)

    # best line of the lyric
    best: Mapped[str | None] = mapped_column(String(200))
    best_status: Mapped[str] = mapped_column(String(16), default='pending', server_default='pending')
    best_note: Mapped[str | None] = mapped_column(String(16))
    # stamped when the row is handed to the external extractor, so that the json
    # import only finalizes rows belonging to an export round and never touches
    # rows that turned pending afterwards.
    best_exported_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    track: Mapped[Optional['Track']] = relationship('Track', back_populates='lyric')

    __table_args__ = (
        Index('ix_lyrics_track_id', 'track_id'),
        Index('ix_lyrics_path', 'path'),
        Index('ix_lyrics_status', 'status'),
        Index('ix_lyrics_best_status', 'best_status'),
        Index('ix_lyrics_tsv', 'lyric_tsv', postgresql_using='gin'),
        CheckConstraint(f"status IN {LYRIC_STATUS}", name='chk_lyrics_status'),
        CheckConstraint(f"best_status IN {BEST_STATUS}", name='chk_lyrics_best_status'),
    )

    def __repr__(self) -> str:
        return f"<Lyric(id={self.id}, track_id={self.track_id}, status={self.status!r})>"
