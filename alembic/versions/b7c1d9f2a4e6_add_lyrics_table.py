"""add lyrics table and chinese full text search configuration

Revision ID: b7c1d9f2a4e6
Revises: 817d80b94905
Create Date: 2026-11-01 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7c1d9f2a4e6'
down_revision: Union[str, Sequence[str], None] = '817d80b94905'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LYRIC_STATUS = ('pending', 'ok', 'review', 'skip', 'failed')
BEST_STATUS = ('pending', 'extracted', 'skip')

# chinese text search configuration used for both indexing and querying.
# only content words are mapped: function words, punctuation, blanks and the
# 'x' bucket (spaces/newlines/single latin letters) are dropped on purpose.
# jieba_stem drops chinese stop words ('是', '的', '我'...) so a query made of
# them only yields an empty tsquery instead of matching every lyric.
TEXT_SEARCH_CONFIG_NAME = 'lyric_cfg'
TEXT_SEARCH_MAPPING_TYPES = (
    'n, nr, ns, nt, nz, ng, nrt, nrfg, '
    'v, vn, vd, vi, vg, '
    'a, ad, an, ag, '
    'd, i, l, j, b, z, zg, t, s, f, '
    'q, mq, vq, m'
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_ts_parser WHERE prsname = 'jieba') THEN
                RAISE EXCEPTION 'pg_jieba is required: text search parser "jieba" not found';
            END IF;
        END
        $$;
        """
    )

    op.create_table(
        'lyrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('dur_delta', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=True),
        sa.Column('source_id', sa.String(length=64), nullable=True),
        sa.Column('fetch_note', sa.Text(), nullable=True),
        sa.Column('written', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('written_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('lyric_plain', sa.Text(), nullable=True),
        sa.Column('lyric_tsv', postgresql.TSVECTOR(), nullable=True),
        sa.Column('best', sa.String(length=200), nullable=True),
        sa.Column('best_status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('best_note', sa.String(length=16), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(f"status IN {LYRIC_STATUS}", name='chk_lyrics_status'),
        sa.CheckConstraint(f"best_status IN {BEST_STATUS}", name='chk_lyrics_best_status'),
        sa.ForeignKeyConstraint(['track_id'], ['tracks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('track_id'),
        sa.UniqueConstraint('path'),
    )
    op.create_index(op.f('ix_lyrics_created_at'), 'lyrics', ['created_at'], unique=False)
    op.create_index(op.f('ix_lyrics_updated_at'), 'lyrics', ['updated_at'], unique=False)
    op.create_index('ix_lyrics_track_id', 'lyrics', ['track_id'], unique=False)
    op.create_index('ix_lyrics_path', 'lyrics', ['path'], unique=False)
    op.create_index('ix_lyrics_status', 'lyrics', ['status'], unique=False)
    op.create_index('ix_lyrics_best_status', 'lyrics', ['best_status'], unique=False)
    op.create_index('ix_lyrics_tsv', 'lyrics', ['lyric_tsv'], unique=False, postgresql_using='gin')

    op.execute(f'DROP TEXT SEARCH CONFIGURATION IF EXISTS {TEXT_SEARCH_CONFIG_NAME}')
    op.execute(f'CREATE TEXT SEARCH CONFIGURATION {TEXT_SEARCH_CONFIG_NAME} (PARSER = jieba)')
    op.execute(
        f'ALTER TEXT SEARCH CONFIGURATION {TEXT_SEARCH_CONFIG_NAME} '
        f'ADD MAPPING FOR {TEXT_SEARCH_MAPPING_TYPES} WITH jieba_stem'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_lyrics_tsv', table_name='lyrics')
    op.drop_index('ix_lyrics_best_status', table_name='lyrics')
    op.drop_index('ix_lyrics_status', table_name='lyrics')
    op.drop_index('ix_lyrics_path', table_name='lyrics')
    op.drop_index('ix_lyrics_track_id', table_name='lyrics')
    op.drop_index(op.f('ix_lyrics_updated_at'), table_name='lyrics')
    op.drop_index(op.f('ix_lyrics_created_at'), table_name='lyrics')
    op.drop_table('lyrics')
    op.execute(f'DROP TEXT SEARCH CONFIGURATION IF EXISTS {TEXT_SEARCH_CONFIG_NAME}')
