"""P2-close item 2: are the two watch-integrity failures a real broken contract?

Two tests fail against the disposable clone `personal_apps_radar_wt`:

    test_deleting_the_account_deletes_its_marks       assert 1 == 0
    test_a_mark_for_an_account_that_does_not_exist_is_an_error
                                                     DID NOT RAISE IntegrityError

Both are the signature of a missing foreign key, and Codex would not accept
"dirty fixtures" without the schema evidence. This script settles it by running
the four scenarios against a **production-compatible schema** on a disposable
MariaDB 10.11.14 -- the same version the target runs.

    PYTHONPATH=. py -3.12 scratchpad/probe_watch_integrity.py

The DDL below is production's own, copied verbatim from `SHOW CREATE TABLE` read
read-only from the target. **No production rows are used or copied**; every row
here is a temporary fixture this script creates and deletes. The same constraint
was confirmed present in the nightly backup, so it survives a restore.

Same guards as the other harnesses: loopback only, never a real schema name,
MariaDB only.
"""
import os
import sys

sys.path.insert(0, '.')

import sqlalchemy as sa                                     # noqa: E402

HOST = os.getenv('REHEARSAL_HOST', '127.0.0.1')
PORT = os.getenv('REHEARSAL_PORT', '3399')
USER = os.getenv('REHEARSAL_USER', 'root')
PASSWORD = os.getenv('REHEARSAL_PASSWORD', '')
SCHEMA = os.getenv('REHEARSAL_SCHEMA', 'radar_watch_probe')

SERVER_URL = f'mysql+pymysql://{USER}:{PASSWORD}@{HOST}:{PORT}/'

# Verbatim from the target, 2026-09-09, read-only.
APP_USER_DDL = """
CREATE TABLE `app_user` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `username` varchar(80) NOT NULL,
  `password_hash` varchar(256) NOT NULL,
  `created_at` datetime NOT NULL,
  `is_admin` tinyint(1) NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
"""

WATCH_DDL_PRODUCTION = """
CREATE TABLE `radar_watch` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` int(11) NOT NULL,
  `ticker` varchar(12) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_radar_watch_user_ticker` (`user_id`,`ticker`),
  KEY `ix_radar_watch_user_id` (`user_id`),
  CONSTRAINT `radar_watch_ibfk_1` FOREIGN KEY (`user_id`)
    REFERENCES `app_user` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
"""

# What the disposable clone actually has: the same table with the constraint
# removed. Kept so the probe can show the failures reproduce there and ONLY
# there, rather than asserting it.
WATCH_DDL_CLONE = WATCH_DDL_PRODUCTION.replace(
    """,
  CONSTRAINT `radar_watch_ibfk_1` FOREIGN KEY (`user_id`)
    REFERENCES `app_user` (`id`) ON DELETE CASCADE""", '')

FAILURES = []


def check(label, condition, detail=''):
    mark = 'PASS' if condition else 'FAIL'
    print(f'  {mark}  {label}' + (f' -- {detail}' if detail else ''))
    if not condition:
        FAILURES.append(label)


def build(engine, watch_ddl):
    with engine.begin() as connection:
        connection.execute(sa.text('drop table if exists radar_watch'))
        connection.execute(sa.text('drop table if exists app_user'))
        connection.execute(sa.text(APP_USER_DDL))
        connection.execute(sa.text(watch_ddl))
        for user_id, name in ((1, 'probe-a'), (2, 'probe-b')):
            connection.execute(
                sa.text('insert into app_user '
                        '(id, username, password_hash, created_at, is_admin) '
                        'values (:i, :u, :p, now(), 0)'),
                {'i': user_id, 'u': name, 'p': 'x'})


def scenarios(engine, label, expect_enforced):
    """The four Codex named, run against whichever schema was built."""
    print(f'\n{label}')

    with engine.begin() as connection:
        connection.execute(sa.text(
            "insert into radar_watch (user_id, ticker, created_at) "
            "values (1, 'NVDA', now()), (1, 'AMD', now()), (2, 'NVDA', now())"))

    # 1. normal add and remove
    with engine.begin() as connection:
        connection.execute(sa.text(
            "delete from radar_watch where user_id = 1 and ticker = 'AMD'"))
        left = connection.execute(sa.text(
            'select count(*) from radar_watch where user_id = 1')).scalar()
    check('normal add and remove works', left == 1, f'{left} row left for user 1')

    # 2. per-account isolation
    with engine.connect() as connection:
        other = connection.execute(sa.text(
            'select count(*) from radar_watch where user_id = 2')).scalar()
    check("one account's removal leaves the other account alone", other == 1)

    # 3. orphan insert
    orphan_rejected = False
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(
                "insert into radar_watch (user_id, ticker, created_at) "
                "values (99999, 'GHOST', now())"))
    except sa.exc.IntegrityError:
        orphan_rejected = True
    check('an orphan mark is refused' if expect_enforced
          else 'an orphan mark is ACCEPTED (no constraint)',
          orphan_rejected == expect_enforced,
          f'rejected={orphan_rejected}')

    # 4. account deletion cascade
    with engine.begin() as connection:
        connection.execute(sa.text('delete from app_user where id = 1'))
        survived = connection.execute(sa.text(
            'select count(*) from radar_watch where user_id = 1')).scalar()
        untouched = connection.execute(sa.text(
            'select count(*) from radar_watch where user_id = 2')).scalar()
    cascaded = survived == 0
    check('deleting the account deletes its marks' if expect_enforced
          else 'deleting the account LEAVES its marks (no constraint)',
          cascaded == expect_enforced,
          f'{survived} marks survived')
    check("the other account's marks survive the cascade", untouched == 1)


def main():
    if HOST not in ('127.0.0.1', 'localhost', '::1'):
        raise SystemExit(f'refusing to run against host {HOST!r}')
    if SCHEMA in ('personal_apps', 'coc_stats'):
        raise SystemExit(f'refusing to use schema {SCHEMA!r}')

    server = sa.create_engine(SERVER_URL, isolation_level='AUTOCOMMIT')
    with server.connect() as connection:
        version = connection.execute(sa.text('select version()')).scalar()
        if 'mariadb' not in version.lower():
            raise SystemExit(f'refusing to rehearse against {version!r}')
        connection.execute(sa.text(f'drop database if exists `{SCHEMA}`'))
        connection.execute(sa.text(
            f'create database `{SCHEMA}` character set utf8mb4'))
    server.dispose()
    print(f'engine: {version}  schema: {SCHEMA} (disposable)')
    print('DDL is the target\'s own, read read-only. No production rows used.')

    engine = sa.create_engine(SERVER_URL + SCHEMA)
    with engine.connect() as connection:
        check('foreign key checks are on',
              connection.execute(sa.text('select @@foreign_key_checks')).scalar()
              == 1)

    build(engine, WATCH_DDL_PRODUCTION)
    scenarios(engine, "against PRODUCTION's schema (constraint present)",
              expect_enforced=True)

    build(engine, WATCH_DDL_CLONE)
    scenarios(engine, 'against the CLONE\'s schema (constraint absent)',
              expect_enforced=False)

    engine.dispose()
    server = sa.create_engine(SERVER_URL, isolation_level='AUTOCOMMIT')
    with server.connect() as connection:
        connection.execute(sa.text(f'drop database `{SCHEMA}`'))
    server.dispose()
    print('\ndisposable schema dropped.')

    print(f'\n{"FAILURES: " + "; ".join(FAILURES) if FAILURES else "all checks passed"}')
    return 1 if FAILURES else 0


if __name__ == '__main__':
    raise SystemExit(main())
