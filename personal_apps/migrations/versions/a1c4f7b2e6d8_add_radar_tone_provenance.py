"""add radar tone provenance and history display diagnostics

`sentiment_model` answers "who judged this mention". Once a backend can
judge relevance without writing tone, that stops answering "whose tone is on
screen", and the post card was rendering a hardcoded 'Claude' for both. The
mention column added here answers the second question; the three history
columns record what a reader was being shown when a judgment was recorded,
which is the other half of the tone comparison the trial owes.

Backfill: where a v2 attitude exists, its tone came from whoever judged the
mention -- no backend that suppresses tone has ever run at this point, so
sentiment_model is exactly right. Rows with only a legacy llm_sentiment
projection and no attitude are left NULL: their tone predates per-model
provenance and guessing an owner would be inventing evidence.

One atomic DDL statement per table per direction, the house rule for radar
migrations: MariaDB commits DDL even when a later statement in the same
migration fails, so a multi-statement upgrade can leave a half-migrated
table that neither upgrade nor downgrade will touch again.

Revision ID: a1c4f7b2e6d8
Revises: e5f8b2ca4d36
Create Date: 2026-09-06
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1c4f7b2e6d8'
down_revision = 'e5f8b2ca4d36'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        'ALTER TABLE radar_mentions '
        'ADD COLUMN sentiment_tone_model VARCHAR(40) NULL')
    op.execute(
        'ALTER TABLE radar_sentiment_judgments '
        'ADD COLUMN displayed_tone VARCHAR(8) NULL, '
        'ADD COLUMN displayed_tone_model VARCHAR(40) NULL, '
        'ADD COLUMN displayed_judged_by VARCHAR(8) NULL')
    # Only where a v2 attitude actually exists. `sentiment_model` is the
    # right answer for those rows and only those.
    op.execute(
        'UPDATE radar_mentions '
        'SET sentiment_tone_model = sentiment_model '
        'WHERE sentiment_attitude IS NOT NULL '
        'AND sentiment_model IS NOT NULL')


def downgrade():
    op.execute(
        'ALTER TABLE radar_sentiment_judgments '
        'DROP COLUMN displayed_tone, '
        'DROP COLUMN displayed_tone_model, '
        'DROP COLUMN displayed_judged_by')
    op.execute(
        'ALTER TABLE radar_mentions DROP COLUMN sentiment_tone_model')
