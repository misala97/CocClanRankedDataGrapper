"""add radar mention events

Revision ID: c489b7c94875
Revises: a53d0b0fcc37
Create Date: 2026-08-26 01:08:03.382750

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = 'c489b7c94875'
down_revision = 'a53d0b0fcc37'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'radar_mention_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=48), nullable=False),
        sa.Column('external_id', sa.String(length=128), nullable=False),
        sa.Column('ticker', sa.String(length=12, collation='utf8mb4_bin'),
                  nullable=False),
        sa.Column('channel', sa.String(length=64), nullable=False,
                  server_default=''),
        sa.Column('created_utc', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('bucket_start', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('author', sa.String(length=64), nullable=True),
        sa.Column('simhash', mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column('confidence', sa.Enum('high', 'low',
                                        name='radar_event_confidence'),
                  nullable=False),
        sa.Column('sentiment', sa.Float(), nullable=True),
        sa.Column('engagement', sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'external_id', 'ticker',
                            name='uq_radar_mention_event'),
        mysql_charset='utf8mb4',
    )
    op.create_index('ix_radar_mention_events_bucket', 'radar_mention_events',
                    ['ticker', 'bucket_start'])
    op.create_index('ix_radar_mention_events_created', 'radar_mention_events',
                    ['created_utc'])


def downgrade():
    op.drop_index('ix_radar_mention_events_created',
                  table_name='radar_mention_events')
    op.drop_index('ix_radar_mention_events_bucket',
                  table_name='radar_mention_events')
    op.drop_table('radar_mention_events')
