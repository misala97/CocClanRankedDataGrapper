"""gym: a declined invite is kept, stamped, until the leader has seen it

Revision ID: e7b2c4d9a1f3
Revises: d6a3f9c2b8e4
Create Date: 2026-09-25 21:00:00.000000

Walkthrough D14 (M5): the leader's live screen carries a line for each
training partner, and an invite that was declined says so there -- "hat
abgelehnt", with an OK -- instead of the partner simply never turning up.
Declining deleted the row, so there was nothing left to say it with.

The row stays, stamped with when it was declined, until the leader taps OK
(which deletes it) or invites the same person again (which clears the
stamp). NULL on every other row, old ones included: none of them was
declined, since a declined one did not survive.

Downgrade drops the column; a kept declined row would then read as a
pending invite again, so those go first.
"""
import sqlalchemy as sa
from alembic import op

revision = 'e7b2c4d9a1f3'
down_revision = 'd6a3f9c2b8e4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('gym_shared_sessions',
                  sa.Column('declined_at', sa.DateTime(), nullable=True))


def downgrade():
    op.execute('DELETE FROM gym_shared_sessions WHERE declined_at IS NOT NULL')
    op.drop_column('gym_shared_sessions', 'declined_at')
