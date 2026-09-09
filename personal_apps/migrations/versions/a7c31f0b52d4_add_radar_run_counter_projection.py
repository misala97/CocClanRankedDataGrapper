"""add the typed counter projection to radar_ingest_runs

Six additive columns beside `summary_json`, which is unchanged and remains the
record. Reading a month of activity meant transferring and decoding every
envelope -- 12,728 rows, 56.8 MiB and ~201 MiB of peak Python heap to return
120 integers. These columns are a typed view of the same data so the read can
name scalars instead.

The backfill is deliberately a Python pass and not a JSON-path UPDATE. The
production engine is MariaDB and the local one MySQL; their JSON functions
differ exactly where this projection is most delicate -- telling an absent key
from a null one -- and that behaviour cannot be verified from the development
environment. Batched by primary key so the pass is bounded whatever the table
holds.

The projection rules below are a FROZEN COPY of features.radar.activity.project
at the time this revision was written. Deliberately not an import: a migration
has to keep producing the same rows years from now, and importing a live
application service would make old history follow current code. The two are
pinned together by a test that runs both over the same envelopes.

An upgrade expects its writers stopped. There is no supported interval in which
the old writer stores envelopes while the new reader reads projections: such a
row would be countable-looking with null counters, which reads as a day whose
totals cannot be answered.

IF THE BACKFILL DIES PART-WAY -- a dropped connection, an OOM, a kill -- the six
columns are already there, because MySQL commits implicitly on `ALTER TABLE`,
and the revision is not stamped. `flask db upgrade` will then fail on a
duplicate column rather than resume. Recovery is to drop the six columns and run
the upgrade again:

    ALTER TABLE radar_ingest_runs
      DROP COLUMN summary_schema_version, DROP COLUMN summary_countable,
      DROP COLUMN posts_seen, DROP COLUMN posts_new,
      DROP COLUMN mentions, DROP COLUMN buckets_written;

Nothing is lost by that: every column this migration writes is derived from
`summary_json`, which it never touches. The refusal path above is different and
needs no recovery -- it runs before any DDL, so a refused upgrade leaves the
schema exactly as it was.

Downgrade drops only these six columns. Every envelope and every other table
survives it, so the projection can be rebuilt by upgrading again -- but the
projection itself is lost, which matters only in that it must be rebuilt, never
in that data is gone.

Revision ID: a7c31f0b52d4
Revises: d82f9afb5898
Create Date: 2026-09-09 18:02:11.480915

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c31f0b52d4'
down_revision = 'd82f9afb5898'
branch_labels = None
depends_on = None

COUNTERS = ('posts_seen', 'posts_new', 'mentions', 'buckets_written')
COUNTER_MAX = 2 ** 63 - 1
BATCH = 500


def _frozen_counter(value):
    """One counter, or None when it is not one. Frozen copy; see the module
    docstring. Out of domain is refused rather than coerced, clamped or turned
    into a zero."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if not 0 <= value <= COUNTER_MAX:
        return None
    return value


def _frozen_project(envelope):
    """(schema_version, countable, counters). Frozen copy; see the docstring."""
    empty = {name: None for name in COUNTERS}
    if not isinstance(envelope, dict):
        return None, False, dict(empty)
    version = envelope.get('schema_version')
    if isinstance(version, bool) or not isinstance(version, int):
        return None, False, dict(empty)
    summary = envelope.get('summary')
    if not isinstance(summary, dict):
        return version, False, dict(empty)
    return version, True, {name: _frozen_counter(summary.get(name))
                           for name in COUNTERS}


def _out_of_domain(envelope):
    """Counter values a stored summary carries that this projection refuses.

    Reported, never repaired. Silently turning a negative or a string into a
    null would rewrite what history says happened, and the shape of such a row
    is a compatibility question for whoever owns the schema, not for a
    migration running unattended.

    Only COUNTABLE envelopes are examined. A row whose envelope is malformed or
    unversioned is never counted by any reader, so whatever sits in its
    counters is not a semantic question -- and blocking an upgrade on junk that
    could never have been read would be an obstruction, not a safeguard.
    """
    version, countable, _ = _frozen_project(envelope)
    if not countable:
        return []
    summary = envelope.get('summary')
    bad = []
    for name in COUNTERS:
        if name not in summary:
            continue
        value = summary[name]
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            bad.append((name, type(value).__name__))
        elif not 0 <= value <= COUNTER_MAX:
            bad.append((name, 'out of range'))
    return bad


def upgrade():
    # The domain scan runs FIRST, before any DDL. MySQL commits implicitly on
    # `ALTER TABLE`, so a refusal raised after the columns were added would
    # leave them present with the revision unstamped -- and the next
    # `flask db upgrade`, after the data was fixed, would fail with a duplicate
    # column instead of retrying. Refusing here leaves the schema untouched and
    # the retry clean.
    _refuse_out_of_domain()

    op.add_column('radar_ingest_runs',
                  sa.Column('summary_schema_version', sa.Integer(),
                            nullable=True))
    # Non-null with a server default of false, so any row inserted by something
    # that does not know this column reads as uncountable rather than unknown.
    op.add_column('radar_ingest_runs',
                  sa.Column('summary_countable', sa.Boolean(), nullable=False,
                            server_default=sa.text('0')))
    for name in COUNTERS:
        op.add_column('radar_ingest_runs',
                      sa.Column(name, sa.BigInteger(), nullable=True))
    _backfill()


def _batches(connection, *columns):
    """Keyset paging by primary key, so the pass is bounded whatever the table
    holds and no OFFSET grows with it.

    The first page is unbounded rather than `id > ''`, because '' is less than
    every other string and that predicate would skip a row whose id is the
    empty string. uuid4 never produces one, but a scan that silently omits a
    row is not the kind of thing to leave resting on that.
    """
    last_id, first = None, True
    while True:
        query = sa.select(*columns).select_from(sa.table('radar_ingest_runs'))
        if not first:
            query = query.where(sa.column('id') > last_id)
        batch = connection.execute(
            query.order_by(sa.column('id')).limit(BATCH)).all()
        if not batch:
            return
        yield batch
        last_id, first = batch[-1].id, False


def _refuse_out_of_domain():
    """Read every stored envelope and refuse if any counter is not one.

    Reported, never repaired. Silently turning a negative or a string into a
    null would rewrite what history says happened, and the shape of such a row
    is a compatibility question for whoever owns the schema, not something a
    migration should settle while running unattended.
    """
    connection = op.get_bind()
    seen, refused = 0, []
    for batch in _batches(connection, sa.column('id'),
                          sa.column('summary_json', sa.JSON)):
        for row in batch:
            seen += 1
            bad = _out_of_domain(row.summary_json)
            if bad:
                refused.append((row.id, bad))
    if not refused:
        return
    # The report names ids and value SHAPES, never stored content.
    shapes = sorted({f'{name}: {kind}'
                     for _, bad in refused for name, kind in bad})
    raise RuntimeError(
        f'{len(refused)} of {seen} radar_ingest_runs carry counter values '
        f'outside the accepted domain (non-negative integers fitting a signed '
        f'BIGINT): {"; ".join(shapes)}. First ids: '
        f'{[run_id for run_id, _ in refused[:5]]}. This is a compatibility '
        f'decision for the schema owner -- the migration refuses rather than '
        f'alter what history says happened. No column has been added and '
        f'nothing has been projected; fix the data and run the upgrade again.')


def _backfill():
    """Project every existing row, in batches, by primary key.

    Only the new columns are written. `summary_json`, `status`, `started_at`,
    `finished_at` and `error_code` are read and never touched, so a row that
    existed before this revision still says exactly what it said.
    """
    connection = op.get_bind()
    runs = sa.table(
        'radar_ingest_runs',
        sa.column('id', sa.String), sa.column('summary_json', sa.JSON),
        sa.column('summary_schema_version', sa.Integer),
        sa.column('summary_countable', sa.Boolean),
        *[sa.column(name, sa.BigInteger) for name in COUNTERS])

    projected = 0
    for batch in _batches(connection, sa.column('id'),
                          sa.column('summary_json', sa.JSON)):
        for row in batch:
            version, countable, counters = _frozen_project(row.summary_json)
            connection.execute(
                sa.update(runs).where(runs.c.id == row.id).values(
                    summary_schema_version=version,
                    summary_countable=countable, **counters))
            projected += 1

    print(f'radar_ingest_runs: projected {projected} rows')


def downgrade():
    for name in reversed(COUNTERS):
        op.drop_column('radar_ingest_runs', name)
    op.drop_column('radar_ingest_runs', 'summary_countable')
    op.drop_column('radar_ingest_runs', 'summary_schema_version')
