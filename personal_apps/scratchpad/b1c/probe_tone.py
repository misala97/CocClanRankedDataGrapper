"""B1C bounded, rollback-only SQL correctness and tone-cost probe.

Requires exact independently registered disposable B1C tuple. Never commits,
never deletes preview data; refuses if its reserved tickers already exist.
"""
import datetime as dt
import json
import math
import pathlib
import statistics
import sys
import time
import tracemalloc
from collections import Counter
from types import SimpleNamespace

APP_DIR = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
import sqlalchemy as sa
from app import app
from extensions import db
from models import RadarPost, RadarMention, RadarMentionEvent, RadarBucketSource
from destructive_target import require
from features.radar.chatter_tone import chart_tone, _event_partitions

NOW = dt.datetime(2026, 9, 13, 12)
SOURCES = ['bluesky', 'reddit:pennystocks']


def insert_events(ticker, count, *, offset=0, buckets=192, source='bluesky'):
    posts, mentions, events = [], [], []
    totals = Counter()
    for i in range(count):
        ident = -2000000000 - offset - i
        when = NOW - dt.timedelta(minutes=15 * (1 + i % buckets))
        ext = f'b1c-probe:{ticker}:{i}'
        posts.append(dict(id=ident, source=source, external_id=ext,
                          channel='b1c-probe', created_utc=when,
                          first_seen=when, last_seen=when))
        mentions.append(dict(id=ident, post_id=ident, ticker=ticker,
                             confidence='high', sentiment_attitude=
                             ['positive', 'negative', 'mixed', None][i % 4]))
        events.append(dict(id=ident, source=source, external_id=ext,
                           ticker=ticker, created_utc=when, bucket_start=when,
                           confidence='high', counts_as_human_chatter=True))
        totals[when] += 1
    for table, rows in [(RadarPost, posts), (RadarMention, mentions),
                        (RadarMentionEvent, events)]:
        for begin in range(0, len(rows), 1000):
            db.session.execute(sa.insert(table.__table__), rows[begin:begin+1000])
    db.session.execute(sa.insert(RadarBucketSource.__table__), [
        dict(ticker=ticker, source=source, bucket_start=when, mention_count=n)
        for when, n in totals.items()])
    return totals


def make_chart(totals, days, step):
    start = NOW - dt.timedelta(days=days)
    values = [0] * (days * 1440 // step)
    for when, count in totals.items():
        index = int((when - start).total_seconds() // (step * 60))
        if 0 <= index < len(values):
            values[index] += count
    return SimpleNamespace(start=start, step_minutes=step, chatter=values)


def correctness():
    ticker = 'B1CTEST'
    totals = insert_events(ticker, 4, offset=40000, buckets=1)
    when = next(iter(totals))
    # One contradictory member invalidates its source bin, including valid peers.
    db.session.execute(sa.update(RadarMention).where(RadarMention.id == -2000040000)
                       .values(sentiment_relevance='irrelevant'))
    chart = make_chart(totals, 1, 15)
    assert chart_tone(ticker, SOURCES, chart, now=NOW)['slots'][-1]['unavailable'] == 4
    # A separate valid source remains coloured.
    insert_events(ticker, 2, offset=41000, buckets=1, source=SOURCES[1])
    chart.chatter[-1] = 6
    slot = chart_tone(ticker, SOURCES, chart, now=NOW)['slots'][-1]
    assert (slot['bullish'], slot['bearish'], slot['unavailable']) == (1, 1, 4)
    # Source-count mismatch must also retain the other source colours.
    db.session.execute(sa.update(RadarMention).where(RadarMention.ticker == ticker)
                       .values(sentiment_relevance='relevant'))
    db.session.execute(sa.update(RadarBucketSource).where(
        RadarBucketSource.ticker == ticker, RadarBucketSource.source == 'bluesky')
        .values(mention_count=5))
    chart.chatter[-1] = 7
    slot = chart_tone(ticker, SOURCES, chart, now=NOW)['slots'][-1]
    assert (slot['bullish'], slot['bearish'], slot['unavailable']) == (1, 1, 5)
    # High OR materialized promotion, and only explicitly false excludes.
    db.session.execute(sa.update(RadarMentionEvent).where(
        RadarMentionEvent.id == -2000040000).values(confidence='low', promoted=True))
    db.session.execute(sa.update(RadarMentionEvent).where(
        RadarMentionEvent.id == -2000040001).values(confidence='low', promoted=False))
    db.session.execute(sa.update(RadarMentionEvent).where(
        RadarMentionEvent.id == -2000040002).values(counts_as_human_chatter=False))
    row = next(r for r in _event_partitions(ticker, SOURCES, when, NOW)
               if r.source == 'bluesky')
    assert row.total == 2 and row.bullish == 1 and row.unjudged == 1
    # Exact retained lower bound excludes older source rows; those totals remain grey.
    old = NOW - dt.timedelta(days=30)
    db.session.execute(sa.insert(RadarBucketSource.__table__),
                       dict(ticker=ticker, source='bluesky', bucket_start=old, mention_count=9))
    long_chart = make_chart({old: 9, when: 7}, 1095, 1440)
    queries = []
    def capture(conn, cursor, statement, parameters, context, many):
        if 'radar_bucket_sources' in statement:
            queries.append((statement, parameters))
    sa.event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        envelope = chart_tone(ticker, SOURCES, long_chart, now=NOW)
    finally:
        sa.event.remove(db.engine, 'before_cursor_execute', capture)
    assert envelope['slots'][-30]['unavailable'] == 9
    assert len(queries) == 1
    assert NOW - dt.timedelta(hours=48) in queries[0][1].values()
    return ['source-bin conflict invalidation', 'other-source colour preserved',
            'source total mismatch', 'high/promoted/false membership',
            'SQL source read retained lower bound', 'old totals unavailable']


def main():
    with app.app_context():
        target = require(db.engine.url)
        assert target == 'localhost:3306/personal_apps_radar_b1c', target
        for table in [RadarBucketSource, RadarMentionEvent, RadarMention]:
            assert db.session.query(table).filter(table.ticker.in_(
                ['B1CTEST', 'B1CBUSY', 'B1CQUIET'])).first() is None
        engine = db.session.execute(sa.text('SELECT VERSION()')).scalar()
        output = dict(engine=engine, target=target, semantics='rollback-only owned fixtures', cases=[])
        try:
            output['checks'] = correctness()
            for ticker, count, offset in [('B1CQUIET', 24, 50000), ('B1CBUSY', 20000, 100000)]:
                totals = insert_events(ticker, count, offset=offset)
                old = NOW - dt.timedelta(days=100)
                db.session.execute(sa.insert(RadarBucketSource.__table__), dict(
                    ticker=ticker, source='bluesky', bucket_start=old, mention_count=100))
                totals[old] = 100
                for label, days, step in [('1D', 1, 15), ('1W', 7, 60), ('3Y', 1095, 1440)]:
                    chart = make_chart(totals, days, step)
                    chart_tone(ticker, SOURCES, chart, now=NOW)
                    timings, query_counts, sizes = [], [], []
                    query_count = [0]
                    def count_query(*args): query_count[0] += 1
                    sa.event.listen(db.engine, 'before_cursor_execute', count_query)
                    try:
                        for _ in range(20):
                            query_count[0] = 0
                            before = time.perf_counter()
                            envelope = chart_tone(ticker, SOURCES, chart, now=NOW)
                            timings.append((time.perf_counter() - before)*1000)
                            query_counts.append(query_count[0])
                            sizes.append(len(json.dumps(envelope).encode()))
                    finally:
                        sa.event.remove(db.engine, 'before_cursor_execute', count_query)
                    tracemalloc.start()
                    chart_tone(ticker, SOURCES, chart, now=NOW)
                    _, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    output['cases'].append(dict(ticker=ticker, events=count, span=label,
                        samples=20, median_ms=statistics.median(timings),
                        p95_ms=sorted(timings)[18], max_ms=max(timings),
                        peak_mib=peak/1024**2, queries=query_counts, bytes=sizes[0]))
            output['scope_limit'] = ('Measures added chart_tone SQL work only, not paired full detail HTTP requests. '
                                     'MySQL timings are not VPS MariaDB proof.')
        finally:
            db.session.rollback()
        for table in [RadarBucketSource, RadarMentionEvent, RadarMention]:
            assert db.session.query(table).filter(table.ticker.in_(
                ['B1CTEST', 'B1CBUSY', 'B1CQUIET'])).first() is None
        output['rollback_verified'] = True
        destination = APP_DIR.parent / 'radar-design/artifacts/b1c-tone-probe.json'
        destination.write_text(json.dumps(output, indent=2))
        print(json.dumps(output, indent=2))

if __name__ == '__main__':
    main()
