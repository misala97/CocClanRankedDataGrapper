"""add sentiment v2 judgment fields, history, meter, journal flag

Revision ID: e7a91c04d2b5
Revises: b3c9d47a1e55
Create Date: 2026-08-31
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = 'e7a91c04d2b5'
down_revision = 'b3c9d47a1e55'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('radar_mentions', sa.Column('sentiment_relevance', sa.String(length=12), nullable=True))
    op.add_column('radar_mentions', sa.Column('sentiment_content_origin', sa.String(length=24), nullable=True))
    op.add_column('radar_mentions', sa.Column('sentiment_attitude', sa.String(length=8), nullable=True))
    op.add_column('radar_mentions', sa.Column('sentiment_expected_move', sa.String(length=8), nullable=True))
    op.add_column('radar_mentions', sa.Column('sentiment_confidence', sa.String(length=8), nullable=True))
    op.add_column('radar_mentions', sa.Column('sentiment_model', sa.String(length=40), nullable=True))
    op.add_column('radar_mentions', sa.Column('sentiment_prompt_version', sa.String(length=64), nullable=True))
    op.add_column('radar_mentions', sa.Column('sentiment_judged_at', mysql.DATETIME(fsp=6), nullable=True))
    op.add_column('radar_mentions', sa.Column('local_sentiment_model_version', sa.String(length=24), nullable=True))
    op.add_column('radar_mentions', sa.Column('review_requested_at', mysql.DATETIME(fsp=6), nullable=True))
    op.create_index('ix_radar_mentions_judged', 'radar_mentions', ['confidence', 'sentiment_judged_at'])
    op.create_check_constraint('ck_radar_mentions_relevance', 'radar_mentions',
        "sentiment_relevance IS NULL OR sentiment_relevance IN ('relevant','irrelevant','uncertain')")
    op.create_check_constraint('ck_radar_mentions_origin', 'radar_mentions',
        "sentiment_content_origin IS NULL OR sentiment_content_origin IN ('human_chatter','broadcast_or_automated','uncertain')")
    op.create_check_constraint('ck_radar_mentions_attitude', 'radar_mentions',
        "sentiment_attitude IS NULL OR sentiment_attitude IN ('positive','negative','mixed','none')")
    op.create_check_constraint('ck_radar_mentions_move', 'radar_mentions',
        "sentiment_expected_move IS NULL OR sentiment_expected_move IN ('up','down','flat','unknown')")
    op.create_check_constraint('ck_radar_mentions_conf', 'radar_mentions',
        "sentiment_confidence IS NULL OR sentiment_confidence IN ('high','medium','low')")

    op.create_table('radar_sentiment_judgments',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('mention_id', sa.BigInteger(), nullable=False),
        sa.Column('stage', sa.String(length=8), nullable=False),
        sa.Column('model', sa.String(length=40), nullable=False),
        sa.Column('prompt_version', sa.String(length=64), nullable=False),
        sa.Column('relevance', sa.String(length=12), nullable=False),
        sa.Column('content_origin', sa.String(length=24), nullable=False),
        sa.Column('attitude', sa.String(length=8), nullable=False),
        sa.Column('expected_move', sa.String(length=8), nullable=False),
        sa.Column('confidence', sa.String(length=8), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False),
        sa.Column('output_tokens', sa.Integer(), nullable=False),
        sa.Column('created_utc', mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(['mention_id'], ['radar_mentions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("stage IN ('primary','review')", name='ck_radar_judgment_stage'),
        sa.CheckConstraint("relevance IN ('relevant','irrelevant','uncertain')",
                           name='ck_radar_judgment_relevance'),
        sa.CheckConstraint("content_origin IN ('human_chatter','broadcast_or_automated','uncertain')",
                           name='ck_radar_judgment_origin'),
        sa.CheckConstraint("attitude IN ('positive','negative','mixed','none')",
                           name='ck_radar_judgment_attitude'),
        sa.CheckConstraint("expected_move IN ('up','down','flat','unknown')",
                           name='ck_radar_judgment_move'),
        sa.CheckConstraint("confidence IN ('high','medium','low')",
                           name='ck_radar_judgment_conf'),
        mysql_charset='utf8mb4',
    )
    op.create_index('ix_radar_sentiment_judgments_mention', 'radar_sentiment_judgments', ['mention_id'])
    op.create_index('ix_radar_sentiment_judgments_created', 'radar_sentiment_judgments', ['created_utc'])

    op.create_table('radar_review_meter',
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('demanded', sa.Integer(), nullable=False),
        sa.Column('attempted', sa.Integer(), nullable=False),
        sa.Column('served', sa.Integer(), nullable=False),
        sa.Column('capped', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('day'),
        mysql_charset='utf8mb4',
    )

    op.add_column('radar_mention_events',
                  sa.Column('counts_as_human_chatter', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('radar_mention_events', 'counts_as_human_chatter')
    op.drop_table('radar_review_meter')
    op.drop_index('ix_radar_sentiment_judgments_created', table_name='radar_sentiment_judgments')
    op.drop_index('ix_radar_sentiment_judgments_mention', table_name='radar_sentiment_judgments')
    op.drop_table('radar_sentiment_judgments')
    for name in ('ck_radar_mentions_relevance', 'ck_radar_mentions_origin',
                 'ck_radar_mentions_attitude', 'ck_radar_mentions_move',
                 'ck_radar_mentions_conf'):
        op.drop_constraint(name, 'radar_mentions', type_='check')
    op.drop_index('ix_radar_mentions_judged', table_name='radar_mentions')
    for name in ('sentiment_relevance', 'sentiment_content_origin',
                 'sentiment_attitude', 'sentiment_expected_move',
                 'sentiment_confidence', 'sentiment_model',
                 'sentiment_prompt_version', 'sentiment_judged_at',
                 'local_sentiment_model_version', 'review_requested_at'):
        op.drop_column('radar_mentions', name)
