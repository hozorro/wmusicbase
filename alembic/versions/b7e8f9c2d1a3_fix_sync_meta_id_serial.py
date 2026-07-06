"""fix sync_meta id column to use serial primary key

Revision ID: b7e8f9c2d1a3
Revises: a1b2c3d4e5f6
Create Date: 2026-07-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e8f9c2d1a3'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix sync_meta: drop old PK on model_name, make id SERIAL PK."""
    # 1. Drop old primary key constraint on model_name
    op.drop_constraint('sync_meta_pkey', 'sync_meta', type_='primary')

    # 2. Create sequence for id column
    op.execute("CREATE SEQUENCE IF NOT EXISTS sync_meta_id_seq OWNED BY sync_meta.id")

    # 3. Backfill existing rows with id = 0 to sequential values
    op.execute(
        "UPDATE sync_meta SET id = sub.rn "
        "FROM (SELECT model_name, ROW_NUMBER() OVER () AS rn FROM sync_meta) sub "
        "WHERE sync_meta.model_name = sub.model_name AND sync_meta.id = 0"
    )

    # 4. Advance sequence past current max id
    op.execute("SELECT setval('sync_meta_id_seq', COALESCE((SELECT MAX(id) FROM sync_meta), 0) + 1, false)")

    # 5. Set server_default to use the sequence
    op.alter_column(
        'sync_meta', 'id',
        server_default=sa.text("nextval('sync_meta_id_seq'::regclass)")
    )

    # 6. Add new primary key on id
    op.create_primary_key('sync_meta_pkey', 'sync_meta', ['id'])


def downgrade() -> None:
    """Revert sync_meta to use model_name as primary key."""
    op.drop_constraint('sync_meta_pkey', 'sync_meta', type_='primary')
    op.alter_column('sync_meta', 'id', server_default=None)
    op.execute("DROP SEQUENCE IF EXISTS sync_meta_id_seq")
    op.create_primary_key('sync_meta_pkey', 'sync_meta', ['model_name'])
