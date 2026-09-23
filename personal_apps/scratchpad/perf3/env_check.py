"""The preflight block every Task 8 script prints before its first number.

It refuses rather than measures. The wrong database, a buffer pool under
2000 MB (at the local default every timing is disk-bound), an index set other
than the deployed three (PERF2 found the held index left behind on its fixture
and every build 0.9 s optimistic), a schema stamp other than the branch head,
or a warm set whose expanded sources do not cover the 24h window -- each one
stops the run.

The limits printed at the bottom belong beside every Task 8 number.
"""
import datetime as dt

import sqlalchemy as sa

import scale_env

DEPLOYED_INDEXES = {'PRIMARY', 'ix_radar_bucket_sources_start',
                    'ix_radar_bucket_sources_coverage'}
MIN_POOL_MB = 2000
STAMP = 'b7e3f9c1a2d4'
# Rows dated this far past the clock are not the fixture's timeline: three
# `reddit:zzarcbf` mention events dated 2027-01-04 are a test's residue.
RESIDUE = dt.timedelta(days=7)

LIMITS = (
    'LIMITS  MySQL 8.0.46 on Windows; the target runs MariaDB 10.11.14, so the'
    ' mechanism transfers and the seconds do not.',
    '        Synthetic perf1-derived fixture, clock-aligned by'
    ' align_scale_fixture.py; hourly buckets, 16,792 rows per hour.',
    '        No radar_posts: tone and the `lean` sort do no real work, so any'
    ' lean timing is a lower bound.',
    "        Source names are the fixture's own (3 real subreddits +"
    ' reddit:sub03..sub32), spelled via the REDDIT_SUBS patch.',
    '        One fixture app_user; watch-profile accounts are created by the'
    ' scripts and deleted afterwards.',
    '        Quotes exist for the US market only (radar_quotes: us/XNAS), so'
    ' DE boards carry no prices.',
)


def _scalar(connection, sql, **params):
    return connection.execute(sa.text(sql), params).scalar()


def preflight(label, *, require_window=True, quiet=False):
    """Bind, check, print the block; return the facts as a dict."""
    app = scale_env.bind(label, require_window=require_window)
    from extensions import db
    from features.radar import config

    now = scale_env.utcnow()
    horizon = now + RESIDUE
    with app.app_context():
        with db.engine.connect() as c:
            facts = {
                'database': db.engine.url.database,
                'engine': _scalar(c, 'SELECT VERSION()'),
                'pool_mb': float(_scalar(
                    c, 'SELECT @@innodb_buffer_pool_size/1048576')),
                'stamp': _scalar(c, 'SELECT version_num FROM alembic_version'),
                'rows': _scalar(c, 'SELECT COUNT(*) FROM radar_bucket_sources'),
                'posts': _scalar(c, 'SELECT COUNT(*) FROM radar_posts'),
                'users': _scalar(c, 'SELECT COUNT(*) FROM app_user'),
                'watches': _scalar(c, 'SELECT COUNT(*) FROM radar_watch'),
                'board_rows': _scalar(
                    c, 'SELECT COUNT(*) FROM radar_board_results'),
                'namespaces': _scalar(
                    c, 'SELECT COUNT(*) FROM radar_board_namespaces'),
            }
            facts['indexes'] = set(c.execute(sa.text(
                'SELECT DISTINCT INDEX_NAME FROM information_schema.STATISTICS'
                ' WHERE TABLE_SCHEMA = DATABASE()'
                " AND TABLE_NAME = 'radar_bucket_sources'")).scalars().all())
            facts['spans'] = {
                'radar_bucket_sources': tuple(c.execute(sa.text(
                    'SELECT MIN(bucket_start), MAX(bucket_start)'
                    ' FROM radar_bucket_sources')).one()),
                'radar_mention_events': tuple(c.execute(sa.text(
                    'SELECT MIN(created_utc), MAX(created_utc)'
                    ' FROM radar_mention_events WHERE created_utc < :h'),
                    {'h': horizon}).one()),
                'radar_quotes': tuple(c.execute(sa.text(
                    'SELECT MIN(fetched_at), MAX(fetched_at)'
                    ' FROM radar_quotes WHERE fetched_at < :h'),
                    {'h': horizon}).one()),
            }
            facts['residue'] = _scalar(
                c, 'SELECT COUNT(*) FROM radar_mention_events'
                   ' WHERE created_utc >= :h', h=horizon)
            facts['windows'] = {
                hours: _scalar(
                    c, 'SELECT COUNT(*) FROM radar_bucket_sources'
                       ' WHERE bucket_start >= :since AND bucket_start < :now',
                    since=now - dt.timedelta(hours=hours), now=now)
                for hours in (24, 12)}
    sources, expanded, covered, total = scale_env.coverage(app, db, config,
                                                           now)
    facts.update(coverage=(covered, total), now=now, **{
        key: scale_env.state()[key]
        for key in ('namespace', 'revision', 'fingerprint', 'subs')})

    extra = sorted(facts['indexes'] - DEPLOYED_INDEXES)
    missing = sorted(DEPLOYED_INDEXES - facts['indexes'])
    if not quiet:
        print('=' * 72)
        print(f'PREFLIGHT  {label}')
        print(f"  database     {facts['database']}   engine {facts['engine']}"
              f"   alembic {facts['stamp']}")
        print(f"  buffer pool  {facts['pool_mb']:.0f} MB (target 2560 MB)")
        print('  indexes      ' + ('deployed three' if not extra and not missing
                                   else f'EXTRA {extra} MISSING {missing}'))
        print(f"  rows         {facts['rows']:,} radar_bucket_sources;"
              f" {facts['posts']} radar_posts; {facts['users']} app_user;"
              f" {facts['watches']} radar_watch")
        for table, (low, high) in facts['spans'].items():
            print(f'  span         {table:22s} {low} -> {high}')
        if facts['residue']:
            print(f"  residue      {facts['residue']} radar_mention_events rows"
                  ' dated more than 7 days ahead (test residue; untouched)')
        print(f"  window rows  24h {facts['windows'][24]:,}   12h"
              f" {facts['windows'][12]:,}   at {now:%Y-%m-%d %H:%M:%S} UTC")
        print(f"  reddit       REDDIT_SUBS patched: {len(facts['subs'])} names;"
              f' warm-set coverage {covered:,} of {total:,}'
              + (' = 100%' if total and covered == total else ' -- NOT 100%'))
        print(f"  namespace    {facts['namespace']}  revision "
              f"{facts['revision'][:12]}  fingerprint {facts['fingerprint']}")
        print(f"  store        {facts['board_rows']} radar_board_results rows,"
              f" {facts['namespaces']} namespaces")
        for line in LIMITS:
            print(line)
        print('=' * 72, flush=True)

    if facts['database'] != scale_env.SCALE_DB:
        raise SystemExit(f"wrong database {facts['database']}")
    if extra or missing:
        raise SystemExit(f'not the deployed index set: extra {extra},'
                         f' missing {missing}')
    if facts['pool_mb'] < MIN_POOL_MB:
        raise SystemExit(f"buffer pool {facts['pool_mb']:.0f} MB < "
                         f'{MIN_POOL_MB} MB')
    if facts['stamp'] != STAMP:
        raise SystemExit(f"schema stamp {facts['stamp']} is not {STAMP}")
    if require_window and (total == 0 or covered != total):
        raise SystemExit(f'coverage {covered} of {total}: align first')
    return facts
