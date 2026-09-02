"""add radar_watch

One row per (account, ticker) the account is watching. Plain DDL: nothing
here that MariaDB parses differently from MySQL.

Revision ID: b7e1c4d9a2f3
Revises: 6a21d4e8c9f0
Create Date: 2026-09-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = 'b7e1c4d9a2f3'
down_revision = '6a21d4e8c9f0'
branch_labels = None
depends_on = None


def upgrade():
    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    op.create_table(
        'radar_watch',
        sa.Column('id', sa.Integer() if is_sqlite else mysql.BIGINT(),
                  primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('app_user.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('ticker',
                  sa.String(length=12,
                            collation=None if is_sqlite else 'utf8mb4_bin'),
                  nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('user_id', 'ticker', name='uq_radar_watch_user_ticker'),
        **({} if is_sqlite else {'mysql_charset': 'utf8mb4'}),
    )
    op.create_index('ix_radar_watch_user_id', 'radar_watch', ['user_id'])


def downgrade():
    op.drop_index('ix_radar_watch_user_id', table_name='radar_watch')
    op.drop_table('radar_watch')
