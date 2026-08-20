"""add low confidence tier

Revision ID: b01b10f20a5b
Revises: ad9c47da1fbd
Create Date: 2026-08-21 00:58:36.902109

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b01b10f20a5b'
down_revision = 'ad9c47da1fbd'
branch_labels = None
depends_on = None


def upgrade():
    # Extraction now emits `low` for a bare token nothing corroborates. Without
    # this the first such mention fails the insert under STRICT_TRANS_TABLES --
    # and no test caught it, because every fixture uses cashtags, which resolve
    # to `high`.
    op.execute("ALTER TABLE radar_mentions "
               "MODIFY confidence ENUM('high','medium','low') NOT NULL")


def downgrade():
    op.execute("DELETE FROM radar_mentions WHERE confidence = 'low'")
    op.execute("ALTER TABLE radar_mentions "
               "MODIFY confidence ENUM('high','medium') NOT NULL")
