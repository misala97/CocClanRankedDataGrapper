"""widen radar source columns

Revision ID: 08316d3e4d77
Revises: 1d26ac48e744
Create Date: 2026-08-27 02:01:16.469834

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '08316d3e4d77'
down_revision = '1d26ac48e744'
branch_labels = None
depends_on = None


def upgrade():
    # Expand before any writer emits `reddit:<sub>`. MySQL/MariaDB DDL is
    # non-transactional, so each MODIFY may commit independently.
    op.alter_column('radar_posts', 'source',
                    existing_type=sa.String(length=16),
                    type_=sa.String(length=48), existing_nullable=False)
    # radar_bucket_sources is PARTITIONED, and `source` is part of its primary
    # key. MODIFY COLUMN rebuilds the table; at ~300k rows that is seconds, but
    # it is not online -- expect the ingest daemon's writes to block briefly.
    op.alter_column('radar_bucket_sources', 'source',
                    existing_type=sa.String(length=24),
                    type_=sa.String(length=48), existing_nullable=False)
    op.alter_column('radar_poll_state', 'source',
                    existing_type=sa.String(length=24),
                    type_=sa.String(length=48), existing_nullable=False)


def downgrade():
    """Narrow the three columns back. NOT semantically lossless -- read this.

    What it restores: old code can write and read Reddit posts again, because
    radar_posts.source is normalised back to the bare `reddit` below.

    What it CANNOT restore: the per-subreddit bucket history. Rows in
    radar_bucket_sources written as `reddit:<sub>` cannot be re-aggregated
    into a single `reddit` row -- each carries its own mention_count,
    distinct_authors, distinct_text_ratio and status, and summing counts while
    taking a max of author counts and a worst-case of statuses invents an
    aggregate that was never observed. They are left under their prefixed
    names, where post-downgrade code reading `source = 'reddit'` will not see
    them: the Reddit history written during the upgraded period reads as
    absent rather than as a wrong number. radar_mention_events keeps its
    prefixed names for the same reason (its column was already 48 and is not
    touched here).

    A re-upgrade therefore recovers the bucket history intact; it is only
    invisible while rolled back.

    WIDTH DEPENDENCY on radar_bucket_sources. Unlike radar_posts, that table
    is narrowed 48 -> 24 with no normalisation, so every prefixed name it
    holds must already fit in 24 characters. The longest configured name is
    `reddit:smallstreetbets` at 22. Adding a subreddit whose name exceeds 17
    characters -- RadarPollState.symbol's own comment cites the
    20-character RobinHoodPennyStocks, which would give a 27-character source
    -- makes this statement fail with MySQL 1406, AFTER the radar_poll_state
    DDL above has already auto-committed. The check below turns that into a
    readable error instead of a half-applied rollback.
    """
    op.alter_column('radar_poll_state', 'source',
                    existing_type=sa.String(length=48),
                    type_=sa.String(length=24), existing_nullable=False)
    too_long = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM radar_bucket_sources "
        "WHERE CHAR_LENGTH(source) > 24")).scalar()
    # int() at the boundary: COUNT is Decimal on MySQL and MariaDB alike.
    if int(too_long or 0):
        raise RuntimeError(
            'radar_bucket_sources holds %d source name(s) longer than 24 '
            'characters; narrowing the column would truncate them. Decide '
            'what those rows should become and delete or rename them before '
            'rolling this migration back.' % int(too_long))
    op.alter_column('radar_bucket_sources', 'source',
                    existing_type=sa.String(length=48),
                    type_=sa.String(length=24), existing_nullable=False)
    # Old code can only write/read aggregate Reddit posts. Atom comment IDs
    # are globally unique, so collapsing the source component cannot collide
    # on uq_radar_post_source_ext.
    op.execute(sa.text(
        "UPDATE radar_posts SET source = 'reddit' "
        "WHERE source LIKE 'reddit:%'"))
    op.alter_column('radar_posts', 'source',
                    existing_type=sa.String(length=48),
                    type_=sa.String(length=16), existing_nullable=False)
