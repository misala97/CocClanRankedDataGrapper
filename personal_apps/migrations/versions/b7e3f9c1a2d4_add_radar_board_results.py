"""add radar board results

Two additive tables for the shared board cache: one control row per cache
generation, and, inside a generation, the published board and queue state for
each exact selection anyone has asked for.

Nothing existing is read or written, so the downgrade is a clean drop of
exactly these two -- results first, then the namespaces they belong to, which
is the order that never leaves a result row addressed to a generation that no
longer exists. There is no data migration and there never will be one: these
tables hold a cache, and a cache whose contents have to be migrated was not a
cache. A rollback loses the stored boards and the producer rebuilds them.

One CREATE per table, one DROP per table, no ALTER. MySQL and MariaDB commit
each DDL statement on its own, so a direction that needs several statements per
table can be interrupted into a shape neither direction will touch again.

`key_json` is TEXT rather than VARCHAR because a legal selection of 37 long
source names writes about 4,000 characters, and a narrower column would
truncate it without failing under a permissive `sql_mode` -- leaving a key that
no longer hashes to the name it is stored under.

Revision ID: b7e3f9c1a2d4
Revises: a7c31f0b52d4
Create Date: 2026-09-10 09:41:12.884301

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision = 'b7e3f9c1a2d4'
down_revision = 'a7c31f0b52d4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'radar_board_namespaces',
        sa.Column('namespace', sa.String(length=64), nullable=False),
        sa.Column('payload_version', sa.SmallInteger(), nullable=False),
        sa.Column('producer_revision', sa.String(length=64), nullable=True),
        sa.Column('created_at', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('last_seen_at', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('producer_owner', sa.String(length=64), nullable=True),
        sa.Column('producer_seen_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('producer_success_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('producer_error', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('namespace'),
        mysql_charset='utf8mb4',
    )
    op.create_table(
        'radar_board_results',
        sa.Column('namespace', sa.String(length=64), nullable=False),
        sa.Column('key_hash', sa.String(length=64), nullable=False),
        sa.Column('key_json', sa.Text(), nullable=False),
        sa.Column('payload_version', sa.SmallInteger(), nullable=False),
        sa.Column('producer_revision', sa.String(length=64), nullable=True),
        sa.Column('queue_state', sa.String(length=16), nullable=False),
        sa.Column('warm', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('as_of', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('built_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('build_ms', sa.Integer(), nullable=True),
        sa.Column('payload', mysql.MEDIUMBLOB(), nullable=True),
        sa.Column('payload_bytes', sa.Integer(), nullable=True),
        sa.Column('enqueued_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('first_demand_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('requested_at', mysql.DATETIME(fsp=6), nullable=False),
        sa.Column('request_count', sa.Integer(), nullable=False,
                  server_default='0'),
        sa.Column('lease_owner', sa.String(length=64), nullable=True),
        sa.Column('lease_token', sa.String(length=32), nullable=True),
        sa.Column('lease_expires_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('attempts', sa.SmallInteger(), nullable=False,
                  server_default='0'),
        sa.Column('next_attempt_at', mysql.DATETIME(fsp=6), nullable=True),
        sa.Column('last_error', sa.String(length=255), nullable=True),
        # The generation comes first in the key as well as in every index: a
        # reader, a producer and the cleaner all work inside one generation,
        # and never across them.
        sa.PrimaryKeyConstraint('namespace', 'key_hash'),
        mysql_charset='utf8mb4',
    )
    # How the producer finds claimable work, and how admission counts the jobs
    # already admitted before deciding whether there is room for one more.
    op.create_index('ix_radar_board_results_queue', 'radar_board_results',
                    ['namespace', 'queue_state', 'next_attempt_at'],
                    unique=False)
    # The warm sweep: which of the standing boards is oldest.
    op.create_index('ix_radar_board_results_warm', 'radar_board_results',
                    ['namespace', 'warm', 'as_of'], unique=False)
    # Eviction: the least recently asked-for on-demand rows, oldest first.
    op.create_index('ix_radar_board_results_demand', 'radar_board_results',
                    ['namespace', 'warm', 'requested_at'], unique=False)


def downgrade():
    # Dropping a table takes its indexes with it. Naming them here as well
    # would only add statements that fail when one is already absent, which is
    # a worse downgrade rather than a more thorough one.
    op.drop_table('radar_board_results')
    op.drop_table('radar_board_namespaces')
