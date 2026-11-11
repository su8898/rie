"""price lists — whole tariff editions held as administrator-maintained reference data

ref_price_list is one edition of a tariff with its source, edition and legal status.
ref_price_list_entry holds its figures, one per code, discipline and price column, with a
description, units and a rand value. ref_price_list_factor holds the conversion factors a list
prints. Holding a list prices nothing: the engine still reads the dated rate store.

Revision ID: a7e1c5d9f468
Revises: c9a4e7f1b632
Create Date: 2026-11-11 10:30:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'a7e1c5d9f468'
down_revision = 'c9a4e7f1b632'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('ref_price_list',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('edition', sa.String(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('legal_status', sa.String(), nullable=False),
    sa.Column('status_note', sa.String(), nullable=False),
    sa.Column('state', sa.String(), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=True),
    sa.Column('effective_to', sa.Date(), nullable=True),
    sa.Column('notes', sa.String(), nullable=False),
    sa.Column('copied_from', sa.Integer(), nullable=True),
    sa.Column('created_by', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('published_by', sa.String(), nullable=False),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('retired_by', sa.String(), nullable=False),
    sa.Column('retired_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_ref_price_list_state'), 'ref_price_list', ['state'], unique=False)
    op.create_table('ref_price_list_factor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('list_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.ForeignKeyConstraint(['list_id'], ['ref_price_list.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('list_id', 'name', name='uq_ref_price_list_factor_name')
    )
    op.create_index(op.f('ix_ref_price_list_factor_list_id'), 'ref_price_list_factor', ['list_id'], unique=False)
    op.create_table('ref_price_list_entry',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('list_id', sa.Integer(), nullable=False),
    sa.Column('seq', sa.Integer(), nullable=False),
    sa.Column('discipline', sa.String(), nullable=False),
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('alt_code', sa.String(), nullable=False),
    sa.Column('price_column', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('units', sa.Float(), nullable=True),
    sa.Column('units_suffix', sa.String(), nullable=False),
    sa.Column('value_rand', sa.Float(), nullable=True),
    sa.Column('unit_of_issue', sa.String(), nullable=False),
    sa.Column('source_page', sa.String(), nullable=False),
    sa.Column('note', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['list_id'], ['ref_price_list.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ref_price_list_entry_code'), 'ref_price_list_entry', ['code'], unique=False)
    op.create_index(op.f('ix_ref_price_list_entry_discipline'), 'ref_price_list_entry', ['discipline'], unique=False)
    op.create_index(op.f('ix_ref_price_list_entry_list_id'), 'ref_price_list_entry', ['list_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ref_price_list_entry_list_id'), table_name='ref_price_list_entry')
    op.drop_index(op.f('ix_ref_price_list_entry_discipline'), table_name='ref_price_list_entry')
    op.drop_index(op.f('ix_ref_price_list_entry_code'), table_name='ref_price_list_entry')
    op.drop_table('ref_price_list_entry')
    op.drop_index(op.f('ix_ref_price_list_factor_list_id'), table_name='ref_price_list_factor')
    op.drop_table('ref_price_list_factor')
    op.drop_index(op.f('ix_ref_price_list_state'), table_name='ref_price_list')
    op.drop_table('ref_price_list')
