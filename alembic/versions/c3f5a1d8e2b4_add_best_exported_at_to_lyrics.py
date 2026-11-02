"""add best_exported_at to lyrics

Revision ID: c3f5a1d8e2b4
Revises: b7c1d9f2a4e6
Create Date: 2026-11-01 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3f5a1d8e2b4'
down_revision: Union[str, Sequence[str], None] = 'b7c1d9f2a4e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'lyrics',
        sa.Column('best_exported_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('lyrics', 'best_exported_at')
