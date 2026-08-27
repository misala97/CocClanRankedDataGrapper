"""widen radar bucket sources baseline days

Revision ID: 35c3ae366677
Revises: 08316d3e4d77
Create Date: 2026-08-27 15:56:10.620302

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '35c3ae366677'
down_revision = '08316d3e4d77'
branch_labels = None
depends_on = None


def upgrade():
    # Float since 2026-08-26. SmallInteger stored span.days, and .days
    # truncated twenty-three hours of history to zero -- which put every row
    # on the board under PROVISIONAL_BASELINE_DAYS permanently (147,228 of
    # 147,429 scored Bluesky rows in production).
    op.alter_column('radar_bucket_sources', 'baseline_days',
                    existing_type=mysql.SMALLINT(),
                    type_=sa.Float(), existing_nullable=True)


def downgrade():
    # DESTRUCTIVE: narrows Float back to SMALLINT, which truncates any
    # fractional value written since the upgrade (e.g. 0.375 -> 0) --
    # silently reversing the fix this migration exists to make (see
    # upgrade()'s comment: SmallInteger truncation put 147,228 of 147,429
    # scored rows under PROVISIONAL_BASELINE_DAYS permanently). Do not run
    # this against a database carrying real scored history.
    op.alter_column('radar_bucket_sources', 'baseline_days',
                    existing_type=sa.Float(),
                    type_=mysql.SMALLINT(), existing_nullable=True)
