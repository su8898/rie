"""coding rules — port of CIE's catalogue-frequency and modifier-pricing rules

ref_code_rule holds one billing rule per tariff code: a once-per-encounter limit, a
time-modifier ladder, or a percentage-of-time modifier. The engine pays a once-only code once
per encounter and prices a time modifier by its ladder.

Revision ID: e5c8f3b0a246
Revises: d4b7e2a91c35
Create Date: 2026-11-10 20:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'e5c8f3b0a246'
down_revision = 'd4b7e2a91c35'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ref_code_rule',
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('rule', sa.String(), nullable=False),
    sa.Column('param', sa.Float(), nullable=False),
    sa.Column('basis', sa.String(), nullable=False),
    sa.Column('origin', sa.String(), nullable=False),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('code')
    )


def downgrade() -> None:
    op.drop_table('ref_code_rule')
