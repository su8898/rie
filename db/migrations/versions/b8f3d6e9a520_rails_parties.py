"""rails parties, batches — port of CIE's provider-intake standard

rails_party registers each connecting party (a provider system or a switch) with its PUBLIC
ES256 key and the providers it may act for. rails_batch stores a batch submission with its
per-claim results. rails_submission records which party signed each submission.

Revision ID: b8f3d6e9a520
Revises: a7e2c5d8f419
Create Date: 2026-11-11 01:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'b8f3d6e9a520'
down_revision = 'a7e2c5d8f419'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('rails_party',
    sa.Column('party_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('public_jwk', sa.JSON(), nullable=False),
    sa.Column('providers', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('party_id')
    )
    op.create_index(op.f('ix_rails_party_status'), 'rails_party', ['status'], unique=False)
    op.create_table('rails_batch',
    sa.Column('batch_id', sa.String(), nullable=False),
    sa.Column('idempotency_key', sa.String(), nullable=False),
    sa.Column('body_hash', sa.String(), nullable=False),
    sa.Column('party_id', sa.String(), nullable=False),
    sa.Column('n_claims', sa.Integer(), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=False),
    sa.Column('results', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('batch_id')
    )
    op.create_index(op.f('ix_rails_batch_idempotency_key'), 'rails_batch', ['idempotency_key'], unique=True)
    op.create_index(op.f('ix_rails_batch_party_id'), 'rails_batch', ['party_id'], unique=False)
    with op.batch_alter_table('rails_submission') as batch:
        batch.add_column(sa.Column('party_id', sa.String(), nullable=True))
        batch.create_index(op.f('ix_rails_submission_party_id'), ['party_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('rails_submission') as batch:
        batch.drop_index(op.f('ix_rails_submission_party_id'))
        batch.drop_column('party_id')
    op.drop_index(op.f('ix_rails_batch_party_id'), table_name='rails_batch')
    op.drop_index(op.f('ix_rails_batch_idempotency_key'), table_name='rails_batch')
    op.drop_table('rails_batch')
    op.drop_index(op.f('ix_rails_party_status'), table_name='rails_party')
    op.drop_table('rails_party')
