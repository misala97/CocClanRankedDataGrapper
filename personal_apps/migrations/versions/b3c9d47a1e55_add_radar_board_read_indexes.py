"""add radar board read indexes

Revision ID: b3c9d47a1e55
Revises: d0a4b9c72e11
Create Date: 2026-08-30

The board build spent 19 of its 20 seconds in two queries that had no index
shaped for them, measured against a production-sized copy (864k bucket-source
rows, 351k journal events):

- ``_covered_hours`` asks radar_bucket_sources for DISTINCT bucket_start by
  source and status.  The existing (bucket_start, source) index cannot serve
  the status filter, so MySQL walked all 854k live index entries and did a
  heap read for each one: 10.8s.  (source, status, bucket_start) is covering
  -- twelve range seeks, no heap reads.
- ``distinct_voices`` asks radar_mention_events for COUNT(DISTINCT author)
  by ticker over a created_utc window.  The only ticker-led index continues
  with bucket_start, so every candidate ticker's whole history was read:
  6.7s.  (ticker, created_utc) seeks straight into the window.

After both: 1.3s.  Expand-only; nothing reads these indexes by name.
"""
from alembic import op


revision = 'b3c9d47a1e55'
down_revision = 'd0a4b9c72e11'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_radar_bucket_sources_coverage', 'radar_bucket_sources',
                    ['source', 'status', 'bucket_start'])
    op.create_index('ix_radar_mention_events_ticker_time',
                    'radar_mention_events', ['ticker', 'created_utc'])


def downgrade():
    op.drop_index('ix_radar_mention_events_ticker_time',
                  table_name='radar_mention_events')
    op.drop_index('ix_radar_bucket_sources_coverage',
                  table_name='radar_bucket_sources')
