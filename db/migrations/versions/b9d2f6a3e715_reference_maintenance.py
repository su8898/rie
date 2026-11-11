"""reference maintenance — the crosswalk as data, and why a code is excluded from flat rates

ref_crosswalk holds the code crosswalk that was a constant in the program: a billed code, the
code whose rate it is paid at, and a status. Only a CONFIRMED entry changes what is paid. The
table is filled from the built-in list when the application first starts on it.

ref_non_bench gains the reason a code is excluded from flat-rate pricing, where the entry came
from, and who added it. The reasons for the codes the loader installs are filled in here.

Revision ID: b9d2f6a3e715
Revises: a7e1c5d9f468
Create Date: 2026-11-11 11:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'b9d2f6a3e715'
down_revision = 'a7e1c5d9f468'
branch_labels = None
depends_on = None

# The loader's own list at the time of this migration (db/load_reference.py), by normalised code.
_LOADER_REASONS = {
    "5": "modifier (multiple procedures)", "6": "modifier (visiting specialist)",
    "8": "assistant (% of surgeon fee)", "9": "assistant (% of surgeon fee)",
    "74": "modifier (endoscopic base)", "133": "add-on (per 15 min)",
    "8007": "assistant (% of fee)", "8008": "after-hours modifier", "8010": "open-reduction modifier",
    "201": "cost of material", "90": "radiology consumables (cost)", "390": "CT contrast (cost)",
    "490": "MR contrast (cost)", "39300": "X-ray films (cost)", "72939": "cost of material",
    "88301": "cost of material", "1830": "hearing aid (global supply)",
    "2": "written report", "6999": "unlisted (comparable code)",
    "4": "discipline code", "84": "discipline code",
    "26": "modifier (one-lung ventilation)",
}


def upgrade() -> None:
    op.create_table('ref_crosswalk',
    sa.Column('code', sa.String(), nullable=False),
    sa.Column('billed_as', sa.String(), nullable=False),
    sa.Column('family', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=False),
    sa.Column('target_code', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('evidence', sa.String(), nullable=False),
    sa.Column('origin', sa.String(), nullable=False),
    sa.Column('updated_by', sa.String(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('confirmed_by', sa.String(), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('code')
    )
    op.create_index(op.f('ix_ref_crosswalk_status'), 'ref_crosswalk', ['status'], unique=False)

    with op.batch_alter_table('ref_non_bench', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reason', sa.String(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('origin', sa.String(), nullable=False, server_default='loader'))
        batch_op.add_column(sa.Column('created_by', sa.String(), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(), nullable=True))

    table = sa.table('ref_non_bench', sa.column('code', sa.String()), sa.column('reason', sa.String()))
    bind = op.get_bind()
    for (code,) in bind.execute(sa.select(table.c.code)).fetchall():
        reason = _LOADER_REASONS.get((code or "").lstrip("0") or "0")
        if reason:
            bind.execute(table.update().where(table.c.code == code).values(reason=reason))


def downgrade() -> None:
    with op.batch_alter_table('ref_non_bench', schema=None) as batch_op:
        batch_op.drop_column('created_at')
        batch_op.drop_column('created_by')
        batch_op.drop_column('origin')
        batch_op.drop_column('reason')
    op.drop_index(op.f('ix_ref_crosswalk_status'), table_name='ref_crosswalk')
    op.drop_table('ref_crosswalk')
