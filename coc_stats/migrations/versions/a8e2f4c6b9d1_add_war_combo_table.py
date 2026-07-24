"""add war_combo table

Revision ID: a8e2f4c6b9d1
Revises: f7a3c9d1e2b4
Create Date: 2026-07-24

"""
import datetime

from alembic import op
import sqlalchemy as sa

revision = 'a8e2f4c6b9d1'
down_revision = 'f7a3c9d1e2b4'
branch_labels = None
depends_on = None

war_combo_table = sa.table(
    'war_combo',
    sa.column('label_a', sa.String),
    sa.column('label_b', sa.String),
    sa.column('score', sa.Integer),
    sa.column('verdict_label', sa.String),
    sa.column('created_at', sa.DateTime),
)

# Sorted-pair seed rows, mirroring the WAR_COMBOS dict being removed from
# features/war/war_combos.py in the same change — recomputed with
# tuple(sorted(...)) so byte-for-byte identical lookups survive the migration.
SEED_ROWS = [
    ('clear', 'clear', 100, 'Flawless'),
    ('clean_up', 'low_clear', 90, 'War Crimes'),
    ('clear', 'low_clear', 90, 'Scaredy Cat'),
    ('clean_up', 'clear', 90, 'Missing Confidence'),
    ('farm', 'low_clear', 75, 'Lazy Farmer'),
    ('clear', 'failed_clear', 50, 'Fumble'),
    ('farm', 'farm', 50, 'Farmer'),
    ('failed_clear', 'low_clear', 50, 'Fumble'),
    ('failed_farm', 'farm', 25, 'Inconsistent Farmer'),
    ('farm', 'wasted', 25, 'Inconsistent Farmer'),
    ('failed_clear', 'failed_clear', 15, 'Failure'),
    ('wasted', 'wasted', 15, 'Wasted'),
    ('no_attack', 'no_attack', 0, 'No Show'),
]


def upgrade():
    op.create_table(
        'war_combo',
        sa.Column('label_a',       sa.String(20), nullable=False),
        sa.Column('label_b',       sa.String(20), nullable=False),
        sa.Column('score',         sa.Integer(),  nullable=False),
        sa.Column('verdict_label', sa.String(60), nullable=False),
        sa.Column('created_at',    sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('label_a', 'label_b'),
    )
    now = datetime.datetime.utcnow()
    op.bulk_insert(war_combo_table, [
        {'label_a': a, 'label_b': b, 'score': s, 'verdict_label': l, 'created_at': now}
        for a, b, s, l in SEED_ROWS
    ])


def downgrade():
    op.drop_table('war_combo')
