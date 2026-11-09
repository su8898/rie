"""engine highs — review 2026-11-09 H2/H6/H7

determinations gain needs_review (an uncovered/unbenchmarked line awaits R&N review),
advisory_signals (visible, non-dispositive reasons) and accident_candidate (the fuzzy WORKLIST
match a human must confirm); billing_lines gain service_date (the cross-claim pay-once ledger
key, s17(5)).

Revision ID: c3a1e7d4b2f0
Revises: 65b69f099fa9
Create Date: 2026-11-09 16:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'c3a1e7d4b2f0'
down_revision = '65b69f099fa9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('billing_lines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('service_date', sa.Date(), nullable=True))

    with op.batch_alter_table('determinations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('needs_review', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column('advisory_signals', sa.JSON(), nullable=False,
                                      server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column('accident_candidate', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('determinations', schema=None) as batch_op:
        batch_op.drop_column('accident_candidate')
        batch_op.drop_column('advisory_signals')
        batch_op.drop_column('needs_review')

    with op.batch_alter_table('billing_lines', schema=None) as batch_op:
        batch_op.drop_column('service_date')
