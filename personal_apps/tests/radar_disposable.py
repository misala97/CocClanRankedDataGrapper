"""Which database a destructive radar suite is allowed to touch.

Six suites here write to whatever is bound: the board-store and producer
suites insert and delete rows, the shared-API suite creates namespaces, the
parity suite seeds sixty tickers and wipes them again, and the two migration
suites run upgrade and downgrade over the whole schema. None of that may ever
run against a database somebody is working in.

The guard used to be a NAME each suite pinned -- `personal_apps_radar_perf3`
in this generation, `personal_apps_radar_wt` in the last -- and to SKIP
anywhere else. Two things were wrong with that.

A pinned name skips SILENTLY, on every machine that is not the one it was
written on, for ever. That is worse than having no guard at all, because a
suite that always skips is a suite nobody is running and nobody can tell.
Task 9b's whole-suite run records five such skips and they are the entire
projection-migration module -- passed over, on the machine where those tests
were written, because a suite one generation younger had pinned a different
name.

And two pinned names cannot both be satisfied by one database, so the two
migration suites could never run in the same pass however the tests were
invoked.

So the rule is inverted. A suite runs wherever it CAN:

  * it SKIPS on a database somebody works in -- the local development database
    and the deployed one share the name `personal_apps`, and `coc_stats` is
    the other application on the same server. Nothing here may write there,
    and the name is the one thing about them that is stable.
  * it FAILS, rather than skipping, on a database that is disposable but does
    not carry the tables it needs. That is a machine where these tests are
    meant to run and whose schema is behind: something to fix in one command,
    not to hide behind a green run.
  * otherwise it RUNS.

The protection is a denylist and not an allowlist on purpose: an allowlist is
exactly the pin this replaces, and its failure mode is the silent skip. The
denylist's failure mode is the opposite -- a new working database would have
to be named here -- and it is the direction where the mistake is visible.
"""
import pytest
import sqlalchemy as sa

from extensions import db

#: Databases these suites must never touch. `personal_apps` is both the local
#: development database and the deployed one; `coc_stats` is the other
#: application sharing the server.
PROTECTED = frozenset({'personal_apps', 'coc_stats'})

#: What to run against a disposable database whose schema is behind.
UPGRADE = 'PYTHONPATH=. FLASK_APP=app.py py -3.12 -m flask db upgrade'


def require(*tables):
    """Say whether this suite may run here, and refuse in the right way.

    Call inside an application context. Returns the database name, so a caller
    that wants to name it in an assertion can.
    """
    database = db.engine.url.database or ''
    if database.lower() in PROTECTED:
        pytest.skip(
            f'{database} is a working database and these tests write to it; '
            'point PERSONAL_DB_NAME at a disposable clone to run them')
    missing = [name for name in tables if not _has(name)]
    if missing:
        pytest.fail(
            f'{database} is disposable but has no {", ".join(missing)}: '
            f'run `{UPGRADE}` against it first')
    return database


def _has(table):
    return sa.inspect(db.engine).has_table(table)
