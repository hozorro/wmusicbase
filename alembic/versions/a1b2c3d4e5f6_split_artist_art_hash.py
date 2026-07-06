"""split artist cover_art_hash into face_art_hash and portrait_art_hash

Revision ID: a1b2c3d4e5f6
Revises: 0aefd99d0f8f
Create Date: 2026-03-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '0aefd99d0f8f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns
    op.add_column('artists', sa.Column('face_art_hash', sa.String(length=40), nullable=True))
    op.add_column('artists', sa.Column('portrait_art_hash', sa.String(length=40), nullable=True))
    
    # Create indexes for new columns
    op.create_index(op.f('ix_artists_face_art_hash'), 'artists', ['face_art_hash'], unique=False)
    op.create_index(op.f('ix_artists_portrait_art_hash'), 'artists', ['portrait_art_hash'], unique=False)
    op.create_index('ix_artists_has_face', 'artists', ['face_art_hash'], unique=False)
    op.create_index('ix_artists_has_portrait', 'artists', ['portrait_art_hash'], unique=False)
    
    # Migrate existing data: copy cover_art_hash to face_art_hash
    op.execute("UPDATE artists SET face_art_hash = cover_art_hash WHERE cover_art_hash IS NOT NULL")
    
    # Drop old column and its indexes
    op.drop_index('ix_artists_has_cover', table_name='artists')
    op.drop_index(op.f('ix_artists_cover_art_hash'), table_name='artists')
    op.drop_column('artists', 'cover_art_hash')


def downgrade() -> None:
    """Downgrade schema."""
    # Re-add old column
    op.add_column('artists', sa.Column('cover_art_hash', sa.String(length=40), nullable=True))
    op.create_index(op.f('ix_artists_cover_art_hash'), 'artists', ['cover_art_hash'], unique=False)
    op.create_index('ix_artists_has_cover', 'artists', ['cover_art_hash'], unique=False)
    
    # Migrate data back
    op.execute("UPDATE artists SET cover_art_hash = face_art_hash WHERE face_art_hash IS NOT NULL")
    
    # Drop new columns and indexes
    op.drop_index('ix_artists_has_portrait', table_name='artists')
    op.drop_index('ix_artists_has_face', table_name='artists')
    op.drop_index(op.f('ix_artists_portrait_art_hash'), table_name='artists')
    op.drop_index(op.f('ix_artists_face_art_hash'), table_name='artists')
    op.drop_column('artists', 'portrait_art_hash')
    op.drop_column('artists', 'face_art_hash')
