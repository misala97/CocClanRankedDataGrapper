"""persist radar quote provider delay

Revision ID: d0a4b9c72e11
Revises: 8b7f2d1c4e90
Create Date: 2026-08-30

Provider freshness is source evidence.  It must survive a later read rather
than being reconstructed from poll timing, while NULL keeps mixed-version
snapshots valid until every writer has deployed.
"""
from alembic import op
import sqlalchemy as sa


revision = 'd0a4b9c72e11'
down_revision = '8b7f2d1c4e90'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('radar_quotes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provider_delay', sa.String(length=8),
                                      nullable=True))


def downgrade():
    with op.batch_alter_table('radar_quotes', schema=None) as batch_op:
        batch_op.drop_column('provider_delay')
