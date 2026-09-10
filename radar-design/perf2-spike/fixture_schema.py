"""Make the fixture's `radar_bucket_sources` match the DEPLOYED schema.

Found on 2026-09-10, part-way through this workstream: the fixture still
carried `ix_radar_bucket_sources_agg`, physically built by PERF1's
`acceptance.py`, which creates it and never drops it. `codex/radar-perf2` does
not carry that migration on purpose -- but the branch's code and the fixture's
storage are two different things, and every build time measured before this
ran was measured WITH the held index present.

The deployed schema is what `models.py` declares:

    ix_radar_bucket_sources_start     (bucket_start, source)
    ix_radar_bucket_sources_coverage  (source, status, bucket_start)
    PRIMARY                           (ticker, bucket_start, source)

`ix_radar_bucket_sources_start` is NOT dropped: Codex's ruling says so
explicitly. Only indexes the deployed schema does not declare are removed.

    python fixture_schema.py            # report
    python fixture_schema.py --fix      # drop what the target does not have
"""
import argparse
import os
import sys
import time

import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_check import bootstrap  # noqa: E402
bootstrap()

from env_check import DB, preflight                    # noqa: E402

TABLE = 'radar_bucket_sources'
DEPLOYED = {'PRIMARY', 'ix_radar_bucket_sources_start',
            'ix_radar_bucket_sources_coverage'}


def present(db):
    rows = db.session.execute(sa.text(
        'SELECT INDEX_NAME, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX)'
        ' FROM information_schema.STATISTICS'
        ' WHERE TABLE_SCHEMA = :s AND TABLE_NAME = :t'
        ' GROUP BY INDEX_NAME'), {'s': DB, 't': TABLE}).fetchall()
    return {name: cols for name, cols in rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fix', action='store_true')
    args = ap.parse_args()
    from app import app
    with app.app_context():
        from extensions import db
        preflight(db, 'fixture schema against the deployed schema')
        found = present(db)
        print('indexes on %s:' % TABLE)
        for name, cols in sorted(found.items()):
            mark = 'deployed' if name in DEPLOYED else '*** NOT DEPLOYED ***'
            print('  %-36s %-8s %s' % (name, mark, cols[:80]))
        extra = sorted(set(found) - DEPLOYED)
        if not extra:
            print('the fixture matches the deployed schema')
            return
        print('\nEXTRA: %s' % ', '.join(extra))
        if not args.fix:
            print('run with --fix to drop them')
            return
        for name in extra:
            began = time.perf_counter()
            db.session.execute(sa.text(
                'ALTER TABLE %s DROP INDEX %s, ALGORITHM=INPLACE, LOCK=NONE'
                % (TABLE, name)))
            db.session.commit()
            print('  dropped %s in %.1f s' % (name,
                                              time.perf_counter() - began))
        db.session.execute(sa.text('ANALYZE TABLE %s' % TABLE))
        db.session.commit()
        print('now: %s' % ', '.join(sorted(present(db))))


if __name__ == '__main__':
    main()
