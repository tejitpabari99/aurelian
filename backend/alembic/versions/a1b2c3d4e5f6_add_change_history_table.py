"""add change_history table

Revision ID: a1b2c3d4e5f6
Revises: 546f84e030c3
Create Date: 2026-03-20 19:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '546f84e030c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'change_history',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('entity_type', sa.String(length=64), nullable=False),
        sa.Column('entity_id', sa.String(length=32), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=16), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('change_source', sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity_type', 'entity_id', 'revision', name='uq_entity_revision'),
    )
    op.create_index(op.f('ix_change_history_id'), 'change_history', ['id'], unique=False)
    op.create_index(op.f('ix_change_history_created_at'), 'change_history', ['created_at'], unique=False)
    op.create_index(op.f('ix_change_history_entity_type'), 'change_history', ['entity_type'], unique=False)
    op.create_index(op.f('ix_change_history_entity_id'), 'change_history', ['entity_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_change_history_entity_id'), table_name='change_history')
    op.drop_index(op.f('ix_change_history_entity_type'), table_name='change_history')
    op.drop_index(op.f('ix_change_history_created_at'), table_name='change_history')
    op.drop_index(op.f('ix_change_history_id'), table_name='change_history')
    op.drop_table('change_history')
