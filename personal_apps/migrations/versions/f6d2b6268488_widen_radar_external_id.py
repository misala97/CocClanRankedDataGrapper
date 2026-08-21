"""widen radar external id

Revision ID: f6d2b6268488
Revises: 38ff07e30e7a
Create Date: 2026-08-21 02:18:01.122181

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6d2b6268488'
down_revision = '38ff07e30e7a'
branch_labels = None
depends_on = None


def upgrade():
    # A Bluesky id is 'bluesky:<did>:<rkey>' and a DID is 32 characters on its
    # own, so the Reddit-sized width truncated -- or, under strict mode,
    # refused the insert outright.
    op.execute("ALTER TABLE radar_posts "
               "MODIFY external_id VARCHAR(128) NOT NULL")


def downgrade():
    op.execute("DELETE FROM radar_posts WHERE CHAR_LENGTH(external_id) > 32")
    op.execute("ALTER TABLE radar_posts "
               "MODIFY external_id VARCHAR(32) NOT NULL")
