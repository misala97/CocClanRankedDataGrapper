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
    """
    if not isinstance(envelope, dict):
        return []
    summary = envelope.get('summary')
    if not isinstance(summary, dict):
        return []
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

    def batches():
        last_id = ''
        while True:
            batch = connection.execute(
                sa.select(runs.c.id, runs.c.summary_json)
                .where(runs.c.id > last_id)
                .order_by(runs.c.id).limit(BATCH)).all()
            if not batch:
                return
            yield batch
            last_id = batch[-1].id

    # Two passes, and the order matters. The first only reads: if any stored
    # counter is outside the accepted domain, the migration refuses BEFORE
    # writing anything, so a refused upgrade leaves no half-projected table
    # behind. MySQL commits implicitly on DDL, so a later raise could not be
    # relied on to undo these updates.
    seen, refused = 0, []
    for batch in batches():
        for row in batch:
            seen += 1
            bad = _out_of_domain(row.summary_json)
            if bad:
                refused.append((row.id, bad))

    if refused:
        # The report names ids and value SHAPES, never stored content.
        shapes = sorted({f'{name}: {kind}'
                         for _, bad in refused for name, kind in bad})
        raise RuntimeError(
            f'{len(refused)} of {seen} radar_ingest_runs carry counter values '
            f'outside the accepted domain (non-negative integers fitting a '
            f'signed BIGINT): {"; ".join(shapes)}. First ids: '
            f'{[run_id for run_id, _ in refused[:5]]}. This is a '
            f'compatibility decision for the schema owner -- the migration '
            f'refuses rather than alter what history says happened. Nothing '
            f'has been projected.')

    projected = 0
    for batch in batches():
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
