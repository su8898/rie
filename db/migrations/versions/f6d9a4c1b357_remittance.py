"""remittance advice — port of CIE's ERA

remittance is the Fund's payment record to one provider for one paid batch; remittance_line
holds each adjudicated line reconciled to what was actually paid.

Revision ID: f6d9a4c1b357
Revises: e5c8f3b0a246
Create Date: 2026-11-10 23:10:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'f6d9a4c1b357'
down_revision = 'e5c8f3b0a246'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('remittance',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ref', sa.String(), nullable=False),
    sa.Column('invoice_ref', sa.String(), nullable=False),
    sa.Column('payment_ref', sa.String(), nullable=False),
    sa.Column('batch_id', sa.Integer(), nullable=False),
    sa.Column('provider_id', sa.String(), nullable=False),
    sa.Column('period_from', sa.Date(), nullable=True),
    sa.Column('period_to', sa.Date(), nullable=True),
    sa.Column('n_claims', sa.Integer(), nullable=False),
    sa.Column('total_billed', sa.Float(), nullable=False),
    sa.Column('total_paid', sa.Float(), nullable=False),
    sa.Column('total_reduced', sa.Float(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('issued_by', sa.String(), nullable=False),
    sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['payment_batch.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('batch_id', 'provider_id', name='uq_remittance_batch_provider')
    )
    op.create_index(op.f('ix_remittance_batch_id'), 'remittance', ['batch_id'], unique=False)
    op.create_index(op.f('ix_remittance_provider_id'), 'remittance', ['provider_id'], unique=False)
    op.create_index(op.f('ix_remittance_ref'), 'remittance', ['ref'], unique=True)
    op.create_index(op.f('ix_remittance_status'), 'remittance', ['status'], unique=False)
    op.create_table('remittance_line',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('remittance_id', sa.Integer(), nullable=False),
    sa.Column('claim_id', sa.String(), nullable=False),
    sa.Column('party_token', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('service_date', sa.Date(), nullable=True),
    sa.Column('billed', sa.Float(), nullable=False),
    sa.Column('paid', sa.Float(), nullable=False),
    sa.Column('reduced', sa.Float(), nullable=False),
    sa.Column('reasons', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['remittance_id'], ['remittance.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_remittance_line_claim_id'), 'remittance_line', ['claim_id'], unique=False)
    op.create_index(op.f('ix_remittance_line_remittance_id'), 'remittance_line', ['remittance_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_remittance_line_remittance_id'), table_name='remittance_line')
    op.drop_index(op.f('ix_remittance_line_claim_id'), table_name='remittance_line')
    op.drop_table('remittance_line')
    op.drop_index(op.f('ix_remittance_status'), table_name='remittance')
    op.drop_index(op.f('ix_remittance_ref'), table_name='remittance')
    op.drop_index(op.f('ix_remittance_provider_id'), table_name='remittance')
    op.drop_index(op.f('ix_remittance_batch_id'), table_name='remittance')
    op.drop_table('remittance')
