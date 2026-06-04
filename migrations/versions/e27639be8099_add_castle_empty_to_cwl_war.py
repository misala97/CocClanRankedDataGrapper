"""add castle_empty to cwl_war

Revision ID: e27639be8099
Revises: 2f372debbd6b
Create Date: 2026-06-04 21:13:31.526872

"""
from alembic import op
import sqlalchemy as sa

revision = 'e27639be8099'
down_revision = '2f372debbd6b'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE cwl_war ADD COLUMN castle_empty TINYINT(1) NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE cwl_war DROP COLUMN castle_empty")
