"""medical reports — port of CIE's statutory medical report forms

medical_report stores a RAF 1 medical report or a RAF 4 serious injury assessment exactly as the
provider filed it, keyed to the claim reference it quoted.

Revision ID: a7e2c5d8f419
Revises: f6d9a4c1b357
Create Date: 2026-11-11 00:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'a7e2c5d8f419'
down_revision = 'f6d9a4c1b357'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('medical_report',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ref', sa.String(), nullable=False),
    sa.Column('form_code', sa.String(), nullable=False),
    sa.Column('form_title', sa.String(), nullable=False),
    sa.Column('provider_id', sa.String(), nullable=False),
    sa.Column('claim_ref', sa.String(), nullable=False),
    sa.Column('claim_id', sa.String(), nullable=True),
    sa.Column('complete', sa.Boolean(), nullable=False),
    sa.Column('missing', sa.JSON(), nullable=False),
    sa.Column('sections', sa.JSON(), nullable=False),
    sa.Column('idempotency_key', sa.String(), nullable=False),
    sa.Column('body_hash', sa.String(), nullable=False),
    sa.Column('received_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_medical_report_claim_id'), 'medical_report', ['claim_id'], unique=False)
    op.create_index(op.f('ix_medical_report_claim_ref'), 'medical_report', ['claim_ref'], unique=False)
    op.create_index(op.f('ix_medical_report_form_code'), 'medical_report', ['form_code'], unique=False)
    op.create_index(op.f('ix_medical_report_idempotency_key'), 'medical_report', ['idempotency_key'], unique=True)
    op.create_index(op.f('ix_medical_report_provider_id'), 'medical_report', ['provider_id'], unique=False)
    op.create_index(op.f('ix_medical_report_ref'), 'medical_report', ['ref'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_medical_report_ref'), table_name='medical_report')
    op.drop_index(op.f('ix_medical_report_provider_id'), table_name='medical_report')
    op.drop_index(op.f('ix_medical_report_idempotency_key'), table_name='medical_report')
    op.drop_index(op.f('ix_medical_report_form_code'), table_name='medical_report')
    op.drop_index(op.f('ix_medical_report_claim_ref'), table_name='medical_report')
    op.drop_index(op.f('ix_medical_report_claim_id'), table_name='medical_report')
    op.drop_table('medical_report')
