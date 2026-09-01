"""add radar market data v2 provenance, shadow, and operational tables

Expand-only stage of the 2026-08-31 market-data design: every column is
nullable or server-defaulted so old writers keep working, and the six
operational tables are unused until their jobs activate. The contraction
belongs to a separate, deliberately delayed migration.

Revision ID: 6a21d4e8c9f0
Revises: f4b2d81c37a9
Create Date: 2026-09-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = '6a21d4e8c9f0'
down_revision = 'f4b2d81c37a9'
branch_labels = None
depends_on = None


def _types():
    is_sqlite = op.get_bind().dialect.name == 'sqlite'
    return {
        'id': sa.Integer() if is_sqlite else mysql.BIGINT(),
        'ts': sa.DateTime() if is_sqlite else mysql.DATETIME(fsp=6),
        'mediumtext': sa.Text() if is_sqlite else mysql.MEDIUMTEXT(),
        'options': {} if is_sqlite else {'mysql_charset': 'utf8mb4'},
    }


def upgrade():
    kinds = _types()

    op.create_table(
        'radar_mapping_generations',
        sa.Column('id', kinds['id'], primary_key=True, autoincrement=True),
        sa.Column('market', sa.String(length=2), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('payload_sha256', sa.String(length=64), nullable=False,
                  unique=True),
        sa.Column('payload_json', kinds['mediumtext'], nullable=False),
        sa.Column('summary_json', sa.Text(), nullable=False),
        sa.Column('created_at', kinds['ts'], nullable=False),
        sa.Column('activated_at', kinds['ts'], nullable=True),
        sa.CheckConstraint(
            "status IN ('shadow', 'active', 'retired', 'failed')",
            name='ck_radar_mapping_generation_status'),
        **kinds['options'],
    )

    op.create_table(
        'radar_market_data_cursors',
        sa.Column('source', sa.String(length=32), primary_key=True),
        sa.Column('mic', sa.String(length=4), primary_key=True),
        sa.Column('channel', sa.String(length=12), primary_key=True),
        sa.Column('remote_id', sa.String(length=160), nullable=False),
        sa.Column('source_ts', kinds['ts'], nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=False),
        sa.Column('fetched_at', kinds['ts'], nullable=False),
        sa.CheckConstraint("channel IN ('pretrade', 'posttrade')",
                           name='ck_radar_market_cursor_channel'),
        **kinds['options'],
    )

    op.create_table(
        'radar_market_data_cycles',
        sa.Column('id', kinds['id'], primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('mic', sa.String(length=4), nullable=False),
        sa.Column('channel', sa.String(length=12), nullable=False),
        sa.Column('scheduled_at', kinds['ts'], nullable=False),
        sa.Column('completed_at', kinds['ts'], nullable=True),
        sa.Column('mode', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('newest_remote_id', sa.String(length=160), nullable=True),
        sa.Column('newest_source_ts', kinds['ts'], nullable=True),
        sa.Column('files_seen', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('files_accepted', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('record_count', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('selected_count', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('rejected_records', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('compressed_bytes', sa.BigInteger(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('uncompressed_bytes', sa.BigInteger(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('parse_ms', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('provider_lag_s', sa.Integer(), nullable=True),
        sa.Column('fetch_lag_s', sa.Integer(), nullable=True),
        sa.Column('error_code', sa.String(length=48), nullable=True),
        sa.UniqueConstraint('source', 'mic', 'channel', 'scheduled_at',
                            name='uq_radar_market_cycle'),
        sa.CheckConstraint("mode IN ('shadow', 'active')",
                           name='ck_radar_market_cycle_mode'),
        sa.CheckConstraint(
            "status IN ('accepted', 'duplicate', 'no_newer', 'rejected',"
            " 'transport_error')",
            name='ck_radar_market_cycle_status'),
        sa.CheckConstraint("channel IN ('pretrade', 'posttrade')",
                           name='ck_radar_market_cycle_channel'),
        **kinds['options'],
    )

    op.create_table(
        'radar_market_trade_events',
        sa.Column('id', kinds['id'], primary_key=True, autoincrement=True),
        sa.Column('mic', sa.String(length=4), nullable=False),
        sa.Column('isin', sa.String(length=12), nullable=False),
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('original_event_id', sa.String(length=64), nullable=True),
        sa.Column('action', sa.String(length=8), nullable=False),
        sa.Column('event_ts', kinds['ts'], nullable=False),
        sa.Column('price', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('volume', sa.BigInteger(), nullable=True),
        sa.Column('is_official_close', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('source_remote_id', sa.String(length=160), nullable=False),
        sa.Column('received_at', kinds['ts'], nullable=False),
        sa.UniqueConstraint('mic', 'event_id',
                            name='uq_radar_market_trade_event'),
        sa.CheckConstraint("action IN ('new', 'correct', 'cancel')",
                           name='ck_radar_trade_event_action'),
        **kinds['options'],
    )
    op.create_index('ix_radar_trade_events_mic_isin_ts',
                    'radar_market_trade_events', ['mic', 'isin', 'event_ts'])
    op.create_index('ix_radar_trade_events_received',
                    'radar_market_trade_events', ['received_at'])

    op.create_table(
        'radar_grouped_close_days',
        sa.Column('id', kinds['id'], primary_key=True, autoincrement=True),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('close_date', sa.Date(), nullable=False),
        sa.Column('is_shadow', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('payload_sha256', sa.String(length=64), nullable=True),
        sa.Column('fetched_at', kinds['ts'], nullable=False),
        sa.Column('completed_at', kinds['ts'], nullable=True),
        sa.Column('provider_rows', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('mapped_rows', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('written_rows', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('unmatched_provider', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('unmatched_universe', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('active_expected', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('active_matched', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('malformed_rows', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('duplicate_conflicts', sa.Integer(), nullable=False,
                  server_default=sa.text('0')),
        sa.Column('error_code', sa.String(length=48), nullable=True),
        sa.Column('http_status', sa.Integer(), nullable=True),
        sa.Column('backoff_until', kinds['ts'], nullable=True),
        sa.UniqueConstraint('source', 'close_date', 'is_shadow',
                            name='uq_radar_grouped_close_day'),
        sa.CheckConstraint(
            "status IN ('accepted', 'no_data', 'rejected',"
            " 'transport_error')",
            name='ck_radar_grouped_day_status'),
        **kinds['options'],
    )

    op.create_table(
        'radar_provider_session_states',
        sa.Column('source', sa.String(length=32), primary_key=True),
        sa.Column('market', sa.String(length=2), primary_key=True),
        sa.Column('last_post_close_session_date', sa.Date(), nullable=True),
        sa.Column('claimed_at', kinds['ts'], nullable=True),
        **kinds['options'],
    )

    with op.batch_alter_table('radar_instruments') as batch:
        batch.add_column(sa.Column('mapping_generation_id', kinds['id'],
                                   nullable=True))
        batch.create_foreign_key(
            'fk_radar_instrument_generation', 'radar_mapping_generations',
            ['mapping_generation_id'], ['id'])

    with op.batch_alter_table('radar_quotes') as batch:
        batch.add_column(sa.Column('source', sa.String(length=32),
                                   nullable=True))
        batch.add_column(sa.Column('price_basis', sa.String(length=8),
                                   nullable=True))
        batch.add_column(sa.Column('bid', sa.Numeric(precision=18, scale=6),
                                   nullable=True))
        batch.add_column(sa.Column('ask', sa.Numeric(precision=18, scale=6),
                                   nullable=True))
        batch.add_column(sa.Column('is_shadow', sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.create_check_constraint(
            'ck_radar_quote_source',
            "source IS NULL OR source IN ('legacy', 'finnhub', 'twelvedata',"
            " 'deutsche_boerse_delayed', 'yahoo_chart')")
        batch.create_check_constraint(
            'ck_radar_quote_price_basis',
            "price_basis IS NULL OR price_basis IN"
            " ('trade', 'midpoint', 'close')")

    with op.batch_alter_table('radar_daily_closes') as batch:
        batch.add_column(sa.Column('source', sa.String(length=32),
                                   nullable=True))
        batch.add_column(sa.Column('price_basis', sa.String(length=8),
                                   nullable=True))
        batch.add_column(sa.Column('adjustment_basis', sa.String(length=8),
                                   nullable=True))
        batch.add_column(sa.Column('is_shadow', sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.drop_constraint('uq_radar_daily_close_market', type_='unique')
        batch.create_unique_constraint(
            'uq_radar_daily_close_market',
            ['ticker', 'market', 'mic', 'close_date', 'is_shadow'])
        batch.create_check_constraint(
            'ck_radar_daily_closes_source',
            "source IS NULL OR source IN ('legacy', 'finnhub', 'twelvedata',"
            " 'deutsche_boerse_delayed', 'yahoo_chart', 'massive_grouped')")
        batch.create_check_constraint(
            'ck_radar_daily_closes_price_basis',
            "price_basis IS NULL OR price_basis = 'close'")
        batch.create_check_constraint(
            'ck_radar_daily_closes_adjustment',
            "adjustment_basis IS NULL OR adjustment_basis = 'split'")


def downgrade():
    # Shadow observations would either collide or become indistinguishable
    # from live rows after their discriminator columns disappear. Live rows
    # are never deleted.
    op.execute(sa.text(
        'DELETE FROM radar_daily_closes WHERE is_shadow = 1'))
    op.execute(sa.text('DELETE FROM radar_quotes WHERE is_shadow = 1'))

    with op.batch_alter_table('radar_daily_closes') as batch:
        batch.drop_constraint('ck_radar_daily_closes_adjustment',
                              type_='check')
        batch.drop_constraint('ck_radar_daily_closes_price_basis',
                              type_='check')
        batch.drop_constraint('ck_radar_daily_closes_source', type_='check')
        batch.drop_constraint('uq_radar_daily_close_market', type_='unique')
        batch.create_unique_constraint(
            'uq_radar_daily_close_market',
            ['ticker', 'market', 'mic', 'close_date'])
        batch.drop_column('is_shadow')
        batch.drop_column('adjustment_basis')
        batch.drop_column('price_basis')
        batch.drop_column('source')

    with op.batch_alter_table('radar_quotes') as batch:
        batch.drop_constraint('ck_radar_quote_price_basis', type_='check')
        batch.drop_constraint('ck_radar_quote_source', type_='check')
        batch.drop_column('is_shadow')
        batch.drop_column('ask')
        batch.drop_column('bid')
        batch.drop_column('price_basis')
        batch.drop_column('source')

    with op.batch_alter_table('radar_instruments') as batch:
        batch.drop_constraint('fk_radar_instrument_generation',
                              type_='foreignkey')
        batch.drop_column('mapping_generation_id')

    op.drop_table('radar_provider_session_states')
    op.drop_table('radar_grouped_close_days')
    op.drop_index('ix_radar_trade_events_received',
                  table_name='radar_market_trade_events')
    op.drop_index('ix_radar_trade_events_mic_isin_ts',
                  table_name='radar_market_trade_events')
    op.drop_table('radar_market_trade_events')
    op.drop_table('radar_market_data_cycles')
    op.drop_table('radar_market_data_cursors')
    op.drop_table('radar_mapping_generations')
