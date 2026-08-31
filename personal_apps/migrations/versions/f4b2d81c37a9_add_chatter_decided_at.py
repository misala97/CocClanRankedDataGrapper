"""add chatter_decided_at to radar_mention_events

The rebuild retry net must key on WHEN eligibility was decided, not when
the event was created: a backfill judging a two-hour-old post, crashing
between the flag commit and the rebuild, was never rediscovered because
recent_decided_windows filtered on created_utc (Codex deploy review,
blocker 2).

Revision ID: f4b2d81c37a9
Revises: e7a91c04d2b5
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = 'f4b2d81c37a9'
down_revision = 'e7a91c04d2b5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('radar_mention_events',
                  sa.Column('chatter_decided_at', mysql.DATETIME(fsp=6),
                            nullable=True))
    op.create_index('ix_radar_mention_events_decided',
                    'radar_mention_events', ['chatter_decided_at'])


def downgrade():
    op.drop_index('ix_radar_mention_events_decided',
                  table_name='radar_mention_events')
    op.drop_column('radar_mention_events', 'chatter_decided_at')
