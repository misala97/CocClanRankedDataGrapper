"""widen ranked_week_analysis.results_json to MEDIUMTEXT

Revision ID: c3d5f7a9b1e3
Revises: b2c4e6f8a0d2
Create Date: 2026-06-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT


# revision identifiers, used by Alembic.
revision = 'c3d5f7a9b1e3'
down_revision = 'b2c4e6f8a0d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ranked_week_analysis', schema=None) as batch_op:
        batch_op.alter_column('results_json', existing_type=sa.Text(), type_=MEDIUMTEXT)


def downgrade():
    with op.batch_alter_table('ranked_week_analysis', schema=None) as batch_op:
        batch_op.alter_column('results_json', existing_type=MEDIUMTEXT, type_=sa.Text())
