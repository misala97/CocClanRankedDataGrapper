"""add is_default_seeded to session sets

Revision ID: c4a7e12f6d93
Revises: b2d5f9c31a42
Create Date: 2026-08-07

"""
from alembic import op
import sqlalchemy as sa

revision = 'c4a7e12f6d93'
down_revision = 'b2d5f9c31a42'
branch_labels = None
depends_on = None


def upgrade():
    # server_default needed so this doesn't fail under MySQL strict mode on a
    # table that already has rows. False is correct for every existing row --
    # this column exists only to let gym_toggle_deload tell an invented
    # default-plan set apart from a real one, and no row predating this
    # migration was ever seeded that way.
    with op.batch_alter_table('gym_session_sets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_default_seeded', sa.Boolean(),
                                       nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('gym_session_sets', schema=None) as batch_op:
        batch_op.drop_column('is_default_seeded')
