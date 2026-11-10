"""dated reference rates — port of CIE's effective-dated rate store

ref_rate_version holds append-only dated versions of a payment-rule rate (RPL tariff x
discipline, negotiated, NAPPI single exit price); ref_rate_log is the immutable change trail.
The engine prices each line at the version in force on its service date.

Revision ID: d4b7e2a91c35
Revises: c3a1e7d4b2f0
Create Date: 2026-11-10 16:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'd4b7e2a91c35'
down_revision = 'c3a1e7d4b2f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ref_rate_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('rate_id', sa.Integer(), nullable=True),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('discipline', sa.String(), nullable=False),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('old_rate', sa.Float(), nullable=True),
    sa.Column('new_rate', sa.Float(), nullable=True),
    sa.Column('old_effective_from', sa.Date(), nullable=True),
    sa.Column('new_effective_from', sa.Date(), nullable=True),
    sa.Column('changed_by', sa.String(), nullable=False),
    sa.Column('note', sa.String(), nullable=False),
    sa.Column('changed_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('ref_rate_log', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ref_rate_log_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_ref_rate_log_rate_id'), ['rate_id'], unique=False)

    op.create_table('ref_rate_version',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('discipline', sa.String(), nullable=False),
    sa.Column('rate', sa.Float(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('origin', sa.String(), nullable=False),
    sa.Column('note', sa.String(), nullable=False),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'kind', 'code', 'discipline', 'effective_from', name='uq_ref_rate_version_key_from')
    )
    with op.batch_alter_table('ref_rate_version', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ref_rate_version_code'), ['code'], unique=False)
        batch_op.create_index(batch_op.f('ix_ref_rate_version_source'), ['source'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('ref_rate_version', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ref_rate_version_source'))
        batch_op.drop_index(batch_op.f('ix_ref_rate_version_code'))

    op.drop_table('ref_rate_version')
    with op.batch_alter_table('ref_rate_log', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ref_rate_log_rate_id'))
        batch_op.drop_index(batch_op.f('ix_ref_rate_log_code'))

    op.drop_table('ref_rate_log')
