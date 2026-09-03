"""add radar_reddit_cursors

One watermark per (subreddit, kind) for the Arctic Shift reader. Plain DDL.

Revision ID: c8d2e5f7a1b4
Revises: b7e1c4d9a2f3
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'c8d2e5f7a1b4'
down_revision = 'b7e1c4d9a2f3'
branch_labels = None
depends_on = None


def upgrade():
    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    stamp = sa.DateTime() if is_sqlite else mysql.DATETIME(fsp=6)
    op.create_table(
        'radar_reddit_cursors',
        sa.Column('sub', sa.String(length=64,
                                   collation=None if is_sqlite else 'utf8mb4_bin'),
                  primary_key=True),
        sa.Column('kind', sa.String(length=12), primary_key=True),
        sa.Column('cursor_utc', stamp, nullable=False),
        sa.Column('updated_at', stamp, nullable=False),
        **({} if is_sqlite else {'mysql_charset': 'utf8mb4'}),
    )


def downgrade():
    op.drop_table('radar_reddit_cursors')
