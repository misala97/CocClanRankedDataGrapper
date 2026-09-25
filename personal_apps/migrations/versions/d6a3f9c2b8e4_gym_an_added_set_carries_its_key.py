"""gym: a set added on the live screen carries the phone's key for it

Revision ID: d6a3f9c2b8e4
Revises: c5f2a8d4e1b7
Create Date: 2026-09-25 01:00:00.000000

Walkthrough D6-A (G-072, G-138): the live screen keeps what the lifter logs
in an outbox on the phone and sends it when the connection lets it -- and
sends it again when an answer was lost on the way back. Every other live
write states a value, so its second copy changes nothing; adding a set is
new work each time, and its second copy was a second set.

The phone names each set it adds. The key is unique per exercise of the
workout, so a copy of an add that already landed finds its set instead of
making another, and two copies racing each other cannot both insert. NULL
on every set added any other way (the debrief, a page from before this);
MariaDB lets a unique index hold any number of NULLs.

Downgrade drops the index and the column; adds are then new work again.
"""
import sqlalchemy as sa
from alembic import op

revision = 'd6a3f9c2b8e4'
down_revision = 'c5f2a8d4e1b7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gym_session_sets',
                  sa.Column('client_key', sa.String(length=36), nullable=True))
    op.create_index('uq_gym_session_sets_client_key', 'gym_session_sets',
                    ['session_exercise_id', 'client_key'], unique=True)


def downgrade():
    # The foreign key on session_exercise_id needs an index that leads with
    # the column. Where InnoDB let its own plain one go once the unique index
    # covered the column, dropping the unique index is refused (error 1553,
    # the trap e4a91c7d20f8 notes): a plain one goes back first.
    indexes = sa.inspect(op.get_bind()).get_indexes('gym_session_sets')
    if not any(ix['column_names'][:1] == ['session_exercise_id'] and not ix.get('unique')
               for ix in indexes):
        op.create_index('session_exercise_id', 'gym_session_sets', ['session_exercise_id'])
    op.drop_index('uq_gym_session_sets_client_key', table_name='gym_session_sets')
    op.drop_column('gym_session_sets', 'client_key')
