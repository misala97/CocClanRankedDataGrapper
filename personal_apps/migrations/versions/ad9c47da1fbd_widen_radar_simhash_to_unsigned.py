"""widen radar simhash to unsigned

Revision ID: ad9c47da1fbd
Revises: 7883c6e08708
Create Date: 2026-08-20 23:59:09.625055

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ad9c47da1fbd'
down_revision = '7883c6e08708'
branch_labels = None
depends_on = None


def upgrade():
    # simhash64() fills all 64 bits, and a signed BIGINT stops at 2**63-1.
    # Signed, an insert fails with "Out of range value for column 'simhash'"
    # for any post whose text happens to hash high -- roughly half of them,
    # which reads as an intermittent fault rather than the systematic one it
    # is.
    op.execute("ALTER TABLE radar_posts "
               "MODIFY simhash BIGINT UNSIGNED NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE radar_posts "
               "MODIFY simhash BIGINT NOT NULL DEFAULT 0")
