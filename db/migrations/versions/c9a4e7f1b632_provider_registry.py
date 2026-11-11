"""practice register — port of CIE's provider identity registry

provider_registry confirms, per practice number, who the practice is, its discipline and setting,
and whether it may bill the Fund. Claim intake derives the fund-side facts from it.

Revision ID: c9a4e7f1b632
Revises: b8f3d6e9a520
Create Date: 2026-11-11 03:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'c9a4e7f1b632'
down_revision = 'b8f3d6e9a520'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('provider_registry',
    sa.Column('provider_id', sa.String(), nullable=False),
    sa.Column('practice_name', sa.String(), nullable=False),
    sa.Column('discipline', sa.String(), nullable=False),
    sa.Column('practice_type', sa.String(), nullable=False),
    sa.Column('setting', sa.String(), nullable=False),
    sa.Column('professional_nr', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('status_reason', sa.String(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('verified', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.String(), nullable=False),
    sa.Column('updated_by', sa.String(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('provider_id')
    )
    op.create_index(op.f('ix_provider_registry_status'), 'provider_registry', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_provider_registry_status'), table_name='provider_registry')
    op.drop_table('provider_registry')
