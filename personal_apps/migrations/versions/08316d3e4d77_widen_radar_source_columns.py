"""widen radar source columns

Revision ID: 08316d3e4d77
Revises: 1d26ac48e744
Create Date: 2026-08-27 02:01:16.469834

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '08316d3e4d77'
down_revision = '1d26ac48e744'
branch_labels = None
depends_on = None


def upgrade():
    # Expand before any writer emits `reddit:<sub>`. MySQL/MariaDB DDL is
    # non-transactional, so each MODIFY may commit independently.
    op.alter_column('radar_posts', 'source',
                    existing_type=sa.String(length=16),
                    type_=sa.String(length=48), existing_nullable=False)
    # radar_bucket_sources is PARTITIONED, and `source` is part of its primary
    # key. MODIFY COLUMN rebuilds the table; at ~300k rows that is seconds, but
    # it is not online -- expect the ingest daemon's writes to block briefly.
    op.alter_column('radar_bucket_sources', 'source',
                    existing_type=sa.String(length=24),
                    type_=sa.String(length=48), existing_nullable=False)
    op.alter_column('radar_poll_state', 'source',
                    existing_type=sa.String(length=24),
                    type_=sa.String(length=48), existing_nullable=False)


def downgrade():
    op.alter_column('radar_poll_state', 'source',
                    existing_type=sa.String(length=48),
                    type_=sa.String(length=24), existing_nullable=False)
    op.alter_column('radar_bucket_sources', 'source',
                    existing_type=sa.String(length=48),
                    type_=sa.String(length=24), existing_nullable=False)
    # Old code can only write/read aggregate Reddit posts. Atom comment IDs
    # are globally unique, so collapsing the source component cannot collide
    # on uq_radar_post_source_ext.
    op.execute(sa.text(
        "UPDATE radar_posts SET source = 'reddit' "
        "WHERE source LIKE 'reddit:%'"))
    op.alter_column('radar_posts', 'source',
                    existing_type=sa.String(length=48),
                    type_=sa.String(length=16), existing_nullable=False)
