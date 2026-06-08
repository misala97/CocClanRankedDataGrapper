"""add war_log_public to cwl_war

Revision ID: a821165b0872
Revises: 08c2e4aac896
Create Date: 2026-06-07 21:42:29.824147

"""
from alembic import op
import sqlalchemy as sa

revision = 'a821165b0872'
down_revision = '08c2e4aac896'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cwl_war', schema=None) as batch_op:
        batch_op.add_column(sa.Column('war_log_public', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('opponent_war_log_public', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('cwl_war', schema=None) as batch_op:
        batch_op.drop_column('opponent_war_log_public')
        batch_op.drop_column('war_log_public')
