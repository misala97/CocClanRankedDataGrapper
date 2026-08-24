"""widen radar_poll_state.symbol for subreddit names

The column was String(12) because everything it tracked was a ticker. Reddit
reuses the same scheduler with the subreddit as the polled unit, and six of the
eighteen configured names are longer than that -- `RobinHoodPennyStocks` is 20
characters -- so `ensure_tracked` failed the whole insert on the daemon's first
cycle and the source produced nothing.

64 rather than 21: Reddit caps subreddit names at 21, but the column's meaning
is now "the thing being polled" rather than "a ticker", and the next source
that reuses this will have its own idea of how long that is. The cost is
nothing -- VARCHAR stores what it holds -- and the primary key at
(24 + 64) * 4 bytes stays far inside InnoDB's index limit.

Widening only. No row can fail to fit a longer column, so this needs no
backfill and the downgrade is only safe while nothing longer than 12 has been
written -- which is why it is written to fail loudly rather than truncate.

Revision ID: d5b81c30fa27
Revises: c7a3e1f92b04
Create Date: 2026-08-24
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd5b81c30fa27'
down_revision = 'c7a3e1f92b04'
branch_labels = None
depends_on = None

TABLE = 'radar_poll_state'
COLUMN = 'symbol'


def upgrade():
    op.alter_column(TABLE, COLUMN,
                    existing_type=sa.String(12, collation='utf8mb4_bin'),
                    type_=sa.String(64, collation='utf8mb4_bin'),
                    existing_nullable=False)


def downgrade():
    # Truncating silently would corrupt the poll schedule for every subreddit
    # whose name does not fit, and a corrupted schedule looks like a source
    # that has simply gone quiet.
    rows = op.get_bind().execute(sa.text(
        f'SELECT COUNT(*) FROM {TABLE} WHERE CHAR_LENGTH({COLUMN}) > 12')).scalar()
    if rows:
        raise RuntimeError(
            f'{rows} rows in {TABLE} have a {COLUMN} longer than 12 characters; '
            'delete them before downgrading or they would be truncated')
    op.alter_column(TABLE, COLUMN,
                    existing_type=sa.String(64, collation='utf8mb4_bin'),
                    type_=sa.String(12, collation='utf8mb4_bin'),
                    existing_nullable=False)
