"""add interval_minutes to uptime_tracker

Revision ID: b4e7d2a91f56
Revises: a8e2f4c6b9d1
Create Date: 2026-08-05 09:00:00.000000

Backfills historical rows so no NULL-fallback path survives in the reader.
Deliberately deletes nothing: this migration runs automatically on every
deploy, and the table holds the 2026-07-31 API outage the Monitor redesign
was built around.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b4e7d2a91f56'
down_revision = 'a8e2f4c6b9d1'
branch_labels = None
depends_on = None

FIXED = {
    'task_update_battle_logs': 5,
    'task_update_clan_members': 5,
    'task_update_ranked_weeks': 10,
}
DYNAMIC = ('task_update_clan_war', 'task_update_cwl', 'task_update_raid_weekend')


def upgrade():
    conn = op.get_bind()

    # MySQL auto-commits DDL, so a failure in the backfill below leaves the
    # column added but the revision unstamped — and a re-run would then die on
    # "duplicate column". Checking first makes the migration re-runnable, which
    # matters because this executes unattended on every deploy.
    existing = {c['name'] for c in sa.inspect(conn).get_columns('uptime_tracker')}
    if 'interval_minutes' not in existing:
        op.add_column('uptime_tracker',
                      sa.Column('interval_minutes', sa.Integer(), nullable=True))

    # Fixed-interval tasks never varied, so their value is exact.
    for fn, minutes in FIXED.items():
        conn.execute(
            sa.text("UPDATE uptime_tracker SET interval_minutes = :m WHERE `function` = :fn"),
            {"m": minutes, "fn": fn},
        )

    # Dynamic tasks: a 'skipped' row is one the task wrote after downshifting to
    # hourly, a 'success' row is one it wrote on the active schedule. Verified
    # against live rows. 'error' rows are left NULL — those are written before
    # the task inspects game state, so it genuinely did not know its schedule.
    conn.execute(
        sa.text(
            "UPDATE uptime_tracker SET interval_minutes = 60 "
            "WHERE `function` IN :fns AND status = 'skipped'"
        ).bindparams(sa.bindparam("fns", expanding=True)),
        {"fns": list(DYNAMIC)},
    )
    conn.execute(
        sa.text(
            "UPDATE uptime_tracker SET interval_minutes = 3 "
            "WHERE `function` IN :fns AND status = 'success'"
        ).bindparams(sa.bindparam("fns", expanding=True)),
        {"fns": list(DYNAMIC)},
    )

    # clan_war's 'warEnded' runs SUCCEED while already on the hourly schedule —
    # the task reschedules before it processes — so the status alone would mark
    # them as 3-minute runs and every legitimate hourly poll afterwards would
    # read as a gap. The summary records the state, so use it.
    conn.execute(sa.text(
        "UPDATE uptime_tracker SET interval_minutes = 60 "
        "WHERE `function` = 'task_update_clan_war' AND status = 'success' "
        "AND summary LIKE 'state=warEnded%'"
    ))


def downgrade():
    conn = op.get_bind()
    existing = {c['name'] for c in sa.inspect(conn).get_columns('uptime_tracker')}
    if 'interval_minutes' in existing:
        op.drop_column('uptime_tracker', 'interval_minutes')
