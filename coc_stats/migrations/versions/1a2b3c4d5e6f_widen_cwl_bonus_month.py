"""widen cwl_bonus.month to fit non-standard CWLSeason keys (double-CWL months)

Revision ID: 1a2b3c4d5e6f
Revises: 0beea7888ed8
Create Date: 2026-06-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = '0beea7888ed8'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('cwl_bonus', 'month',
                     existing_type=sa.String(7),
                     type_=sa.String(20),
                     existing_nullable=False)


def downgrade():
    op.alter_column('cwl_bonus', 'month',
                     existing_type=sa.String(20),
                     type_=sa.String(7),
                     existing_nullable=False)
