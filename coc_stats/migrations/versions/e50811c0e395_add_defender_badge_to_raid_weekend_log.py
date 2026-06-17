"""add defender_badge to raid_weekend_log

Revision ID: e50811c0e395
Revises: a4f6c8e2d1b3
Create Date: 2026-06-07 17:41:45.148029

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e50811c0e395'
down_revision = 'a4f6c8e2d1b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('raid_weekend_log', schema=None) as batch_op:
        batch_op.add_column(sa.Column('defender_badge', sa.String(length=255), nullable=True))

    # Delete the most recent raid weekend (and its logs) so the next sync repopulates with badge URLs
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT id FROM raid_weekend ORDER BY start_time DESC LIMIT 1"
    ))
    row = result.fetchone()
    if row:
        raid_id = row[0]
        conn.execute(sa.text("DELETE FROM raid_weekend_log WHERE raid_weekend_id = :id"), {"id": raid_id})
        conn.execute(sa.text("DELETE FROM raid_weekend WHERE id = :id"), {"id": raid_id})


def downgrade():
    with op.batch_alter_table('raid_weekend_log', schema=None) as batch_op:
        batch_op.drop_column('defender_badge')
