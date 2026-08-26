"""add promoted to radar mention events

Revision ID: 1d26ac48e744
Revises: c489b7c94875
Create Date: 2026-08-26 14:10:31.073316

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1d26ac48e744'
down_revision = 'c489b7c94875'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('radar_mention_events',
                  sa.Column('promoted', sa.Boolean(), nullable=False,
                            server_default=sa.text('0')))


def downgrade():
    op.drop_column('radar_mention_events', 'promoted')
