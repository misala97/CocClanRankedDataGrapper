"""MD-SELECTED-PRICE-IMPLEMENT-1 browser QA fixtures -- SYNTHETIC.

    py -3.12 radar-design/artifacts/md-selected-price-implementation/browser/fixtures.py

Writes the API answers verify_browser.py serves to the built hub. Every
price-chart answer is the REAL reader/contract output
(features.radar.price_chart_reader.build_response) over the unit suite's fake
store and fake admission -- not a hand-drawn showcase. Yahoo series are the
SAVED research arrays (tests/selected_price_unit/fixtures/yahoo_saved_arrays.json,
captured 2026-09-15 by the Researcher) normalized with synthetic meta; chatter,
tone, quotes, closes, detail and board payloads are synthetic. Nothing here
contacts a provider, a database or production.
"""
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PERSONAL = ROOT / 'personal_apps'
sys.path.insert(0, str(PERSONAL))
sys.path.insert(0, str(PERSONAL / 'tests'))

from features.radar import price_chart_contract as c  # noqa: E402
from features.radar import price_chart_reader as reader  # noqa: E402
from selected_price_unit.helpers import (  # noqa: E402
    FakeAdmission, FakeStore, bucket, company_row, instrument_row, tone_row)

UTC = dt.timezone.utc
OUT = HERE / 'fixtures'
SAVED = json.loads((PERSONAL / 'tests' / 'selected_price_unit' / 'fixtures'
                    / 'yahoo_saved_arrays.json').read_text(encoding='utf-8'))
SOURCES = ['bluesky', 'fourchan', 'reddit:wallstreetbets']
QUARTER = dt.timedelta(minutes=15)


def utc(*parts):
    return dt.datetime(*parts, tzinfo=UTC)


def naive(when):
    return when.astimezone(UTC).replace(tzinfo=None)


COMPANIES = {
    'AAPL': dict(name='Apple Inc', venue='NASDAQ', mic='XNMS', exchange='NASDAQ', price=330.46),
    'MSFT': dict(name='Microsoft Corp', venue='NASDAQ', mic='XNGS', exchange='NASDAQ', price=431.18),
    'NVDA': dict(name='NVIDIA Corp', venue='NASDAQ', mic='XNMS', exchange='NASDAQ', price=121.07),
    'BRK.B': dict(name='Berkshire Hathaway Inc Class B',
                  venue='New York Stock Exchange, Main Market (Consolidated Tape A listing)',
                  mic='XNYS', exchange='NYSE', price=514.97),
    'TSLA': dict(name='Tesla Inc', venue='NASDAQ', mic='XNMS', exchange='NASDAQ', price=248.5),
}


def saved_series(key, symbol, exchange, ticker, window, received):
    info = COMPANIES[ticker]
    saved = SAVED['series'][key]
    payload = {'chart': {'result': [{
        'meta': {'symbol': symbol, 'currency': 'USD', 'exchangeName': exchange},
        'timestamp': saved['timestamp'], 'indicators': {'quote': [{'close': saved['close']}]}}]}}
    spec = c.request_spec({'provider_symbol': ticker, 'currency': 'USD', 'mic': info['mic']}, window)
    result = c.normalize_yahoo(payload, spec, received_at=received.timestamp())
    assert result['kind'] == 'ok', result
    return result


def buckets_for(window, *, seed=0, quiet=(), missing=(), truncated=(), config_switch=None,
                overlap_at=None, off_grid=False):
    rows = []
    cursor, end = naive(window.start), naive(window.end)
    index = 0
    while cursor < end:
        busy = 13 <= cursor.hour < 21
        for n, source in enumerate(SOURCES):
            if any(a <= cursor < b for a, b in quiet):
                continue
            count = (index * (3 + n) + seed) % (4 + 2 * n) + (3 if busy and n != 1 else 0)
            status = 'ok'
            if source == 'fourchan' and cursor in missing:
                status = 'missing'
            if source == 'reddit:wallstreetbets' and cursor in truncated:
                status = 'truncated'
            config = 'v2' if config_switch is not None and cursor >= config_switch else 'v1'
            rows.append(bucket(cursor, source, count, status, config))
        if overlap_at is not None and cursor == overlap_at:
            rows.append(bucket(cursor, 'reddit', 2))
        cursor += QUARTER
        index += 1
    if off_grid:
        rows.append(bucket(naive(window.start) + dt.timedelta(minutes=7), 'bluesky', 1))
    return rows


def tone_for(rows, now):
    lower = naive(now) - dt.timedelta(hours=48)
    out = []
    for row in rows:
        if row['bucket_start'] < lower or row['status'] == 'missing' or row['source'] == 'reddit':
            continue
        n = row['mention_count']
        bullish, bearish = n // 2, n // 5
        unjudged = 1 if n >= 4 else 0
        out.append(tone_row(row['bucket_start'], row['source'], bullish=bullish, bearish=bearish,
                            unjudged=unjudged, neutral=n - bullish - bearish - unjudged))
    return out


def quotes_for(window, mic, *, start_price, gap):
    rows, price, k = [], start_price, 0
    cursor = naive(window.start)
    while cursor <= naive(window.end) - dt.timedelta(seconds=30):
        if not (gap[0] <= cursor < gap[1]):
            price = round(price + ((k * 37) % 11 - 5) * 0.07, 2)
            rows.append({'quote_ts': cursor, 'price': price, 'source': 'finnhub', 'price_basis': 'trade',
                         'currency': 'USD', 'market': 'us', 'mic': mic,
                         'fetched_at': cursor + dt.timedelta(seconds=20), 'is_shadow': False})
        cursor += dt.timedelta(minutes=5)
        k += 1
    return rows


def build(ticker, span, now, admission, **store):
    info = COMPANIES[ticker]
    fake = FakeStore(companies=[company_row(symbol=ticker, name=info['name'])],
                     instruments=[instrument_row(ticker=ticker, provider_symbol=ticker, mic=info['mic'],
                                                 venue=info['venue'])], **store)
    reader.clear_local_cache()
    payload = reader.build_response(ticker, SOURCES, span, now, coordinator=FakeAdmission(admission),
                                    store=fake)
    assert len(fake.calls) <= 8
    return payload


def answer(state, retry=None, reason=None, series=None):
    return {'state': state, 'retry_after_seconds': retry, 'reason': reason, 'series': series}


def states():
    out = {}

    now = utc(2026, 9, 15, 13, 50, 19)
    window = c.window_for('1W', now)
    series = saved_series('yahoo_5d_5m_AAPL', 'AAPL', 'NMS', 'AAPL', window, now)
    rows = buckets_for(window, seed=1, missing={naive(utc(2026, 9, 11, 15, 0))},
                       quiet=[(naive(utc(2026, 9, 12, 4)), naive(utc(2026, 9, 12, 9)))])
    out['ordinary'] = dict(ticker='AAPL', span='1W', now=now, description=(
        '1W ready: saved AAPL 5d/5m arrays (one null bar, one off-grid point), five sessions, today partial; '
        'three sources with a quiet outage and a missing bucket'),
        payload=build('AAPL', '1W', now, answer('ready', series=series), buckets=rows, tone=tone_for(rows, now)))

    now = utc(2026, 9, 15, 13, 50, 21)
    window = c.window_for('1D', now)
    series = saved_series('yahoo_1d_1m_AAPL', 'AAPL', 'NMS', 'AAPL', window, now)
    rows = buckets_for(window, seed=2, truncated={naive(utc(2026, 9, 15, 12, 15))},
                       quiet=[(naive(utc(2026, 9, 15, 9, 30)), naive(utc(2026, 9, 15, 10, 30)))],
                       overlap_at=naive(utc(2026, 9, 15, 11, 0)))
    out['partial_gap'] = dict(ticker='AAPL', span='1D', now=now, description=(
        '1D ready, current session so far: saved AAPL 1d/1m extended-hours arrays with missing minutes and a '
        'null bar; an hour with no bucket rows (unknown), a truncated bucket and a Reddit overlap'),
        payload=build('AAPL', '1D', now, answer('ready', series=series), buckets=rows, tone=tone_for(rows, now)))

    now = utc(2026, 9, 15, 13, 54, 30)
    received = utc(2026, 9, 15, 13, 50, 21)
    window = c.window_for('1D', now)
    series = saved_series('yahoo_1d_1m_AAPL', 'AAPL', 'NMS', 'AAPL', window, received)
    rows = buckets_for(window, seed=2)
    out['stale'] = dict(ticker='AAPL', span='1D', now=now, description=(
        '1D cached provider series received 249 s before the answer (stale) while a refresh is pending'),
        payload=build('AAPL', '1D', now, answer('pending', 2, 'refreshing an aged series', series),
                      buckets=rows, tone=tone_for(rows, now)))

    now = utc(2026, 9, 15, 15, 12)
    window = c.window_for('1D', now)
    rows = buckets_for(window, seed=3)
    out['fallback'] = dict(ticker='MSFT', span='1D', now=now, description=(
        '1D provider acquisition pending: stored Finnhub quotes of the same XNGS instrument as the '
        'coherent fallback, with a 90-minute gap'),
        payload=build('MSFT', '1D', now, answer('pending', 2, 'acquiring'), buckets=rows,
                      tone=tone_for(rows, now),
                      quotes=quotes_for(window, 'XNGS', start_price=429.4,
                                        gap=(naive(utc(2026, 9, 15, 11)), naive(utc(2026, 9, 15, 12, 30))))))

    window = c.window_for('1W', now)
    rows = buckets_for(window, seed=4, quiet=[(naive(utc(2026, 9, 10, 0)), naive(utc(2026, 9, 11, 12)))])
    out['unavailable'] = dict(ticker='NVDA', span='1W', now=now, description=(
        '1W provider backoff (retry after 120 s), no stored daily close in the window: price null with its '
        'reason; a day and a half of unknown chatter'),
        payload=build('NVDA', '1W', now, answer('backoff', 120, 'the provider throttled this process'),
                      buckets=rows, tone=tone_for(rows, now)))

    rows = buckets_for(window, seed=5, config_switch=naive(utc(2026, 9, 11, 16)),
                       overlap_at=naive(utc(2026, 9, 14, 14, 30)), off_grid=True)
    daily = [{'close_date': d, 'close': 512.0 + i * 1.7, 'currency': 'USD', 'source': 'massive_grouped',
              'price_basis': 'close', 'adjustment_basis': 'split',
              'fetched_at': dt.datetime.combine(d, dt.time(23)), 'market': 'us', 'mic': 'XNYS',
              'is_shadow': False}
             for i, d in enumerate([dt.date(2026, 9, 9), dt.date(2026, 9, 10), dt.date(2026, 9, 11),
                                    dt.date(2026, 9, 14)])]
    out['long'] = dict(ticker='BRK.B', span='1W', now=now, description=(
        '1W provider switched off: stored daily closes as separate dots, a long venue name, a source '
        'configuration change, a Reddit overlap and an off-grid row (several data notes)'),
        payload=build('BRK.B', '1W', now, answer('disabled', reason='provider acquisition is switched off'),
                      buckets=rows, tone=tone_for(rows, now), daily=daily))
    return out


def quote(ticker):
    info = COMPANIES[ticker]
    return {'market': 'us', 'venue': info['venue'] if len(info['venue']) < 20 else 'NYSE', 'mic': info['mic'],
            'currency': 'USD', 'price': info['price'], 'regular_move': 0.0123, 'extended_move': None,
            'session': 'regular', 'quality': 'delayed', 'age_seconds': 900,
            'quoted_at': '2026-09-15T13:35:00Z', 'tape_status': 'ok', 'score_eligible': True,
            'score_term': 'divergence', 'is_fallback': False, 'source': 'finnhub',
            'price_basis': 'trade', 'bid': None, 'ask': None}


def row(ticker, rank):
    return {
        'ticker': ticker, 'name': COMPANIES[ticker]['name'], 'segment': 'large', 'divergence': 0.4,
        'mention_z': 4.0 - rank * 0.5, 'mentions': 40 - rank * 5, 'expected': 9, 'ratio': 3.1,
        'authors': 12, 'text_ratio': 0.9, 'sources': ['bluesky', 'reddit'],
        'activity_sources': ['bluesky', 'reddit'], 'price': COMPANIES[ticker]['price'],
        'price_move': 0.012, 'direction': 'up', 'price_status': 'ok', 'quote': quote(ticker),
        'baseline_days': 30, 'marks': [], 'eligible': True,
        'series': [{'hour': f'2026-09-15T{h:02d}:00:00Z', 'count': (h * 7) % 9} for h in range(24)],
        'price_series': [None] * 24, 'normal_per_hour': 1.2,
        'triplet': {'1': 1.1, '4': 2.0, '24': 1.6}, 'tone': {'bullish': 6, 'neutral': 10, 'bearish': 3},
        'clauses': [{'kind': 'ratio', 'text': '3.1x its normal'}, {'kind': 'venues', 'text': '2 venues'}],
    }


def board():
    return {
        'generated_at': '2026-09-15T13:50:00Z', 'market': 'us', 'display_timezone': 'Europe/Berlin',
        'market_venue': 'US markets', 'next_boundary_label': 'closes',
        'next_boundary_at': '2026-09-15T20:00:00Z', 'sources': ['bluesky', 'fourchan', 'reddit'],
        'all_sources': ['bluesky', 'fourchan', 'reddit'], 'segments': [], 'session': 'regular',
        'window_hours': 4, 'min_venues': 1, 'venue_counts': {'any': 5, 'multi': 3}, 'sort': None,
        'dir': 'desc', 'segment_counts': {'all': 5, 'large': 5}, 'triplet_hours': [1, 4, 24],
        'series_hours': 24, 'lead_count': 3,
        'rows': [row(t, i) for i, t in enumerate(COMPANIES)], 'excluded': {}, 'watching': [], 'watch_rows': [],
        'shared': False, 'pending': False, 'busy': False, 'stale': False, 'failed': False,
        'as_of': '2026-09-15T13:50:00Z', 'built_at': '2026-09-15T13:50:00Z', 'age_seconds': 0,
        'fresh_seconds': 120, 'hard_expiry_seconds': 600, 'retry_after_ms': None,
        'queue_age_seconds': None, 'ops_collected_at': '2026-09-15T13:50:00Z',
    }


def detail(ticker, span):
    info = COMPANIES[ticker]
    slots, step = (96, 15) if span == '1D' else (168, 60)
    start = utc(2026, 9, 15, 13, 50) - dt.timedelta(minutes=slots * step)
    return {
        'market': 'us', 'display_timezone': 'Europe/Berlin',
        'identity': {'ticker': ticker, 'name': info['name'], 'exchange': info['exchange'],
                     'segment': 'large', 'market_cap': 2.9e12, 'ipo_date': '1980-12-12',
                     'price': info['price'], 'price_move': 0.0123, 'price_status': 'ok',
                     'session': 'regular', 'quote': quote(ticker)},
        'read': [{'kind': 'plain', 'text': f'{ticker} is being discussed more than usual.'}],
        'chart': {'from': c.iso_z(start), 'span': span, 'step_minutes': step,
                  'closes': [round(info['price'] - 2 + (i % 7) * 0.4, 2) if i % 5 else None for i in range(slots)],
                  'chatter': [(i * 3) % 7 for i in range(slots)], 'sessions': [], 'currency': 'USD',
                  'basis_venue': None, 'converted_from': None, 'priced_from': 'intraday',
                  'normal_per_slot': None, 'watched_from': '2026-08-01'},
        'breakdown': {'venues': [{'source': 'bluesky', 'mentions': 20, 'voices': 9},
                                 {'source': 'reddit', 'mentions': 18, 'voices': 11}],
                      'bullish': 12, 'neutral': 20, 'bearish': 6, 'disagreements': 2,
                      'top_author_share': 0.18, 'top_two_share': 0.3, 'peak_hour': '2026-09-15T13:00:00Z',
                      'peak_count': 9, 'first_seen': '2026-08-01', 'mentions': 38, 'voices': 20},
        'posts': [], 'post_total': 0,
    }


def main():
    OUT.mkdir(exist_ok=True)
    manifest = {'synthetic': True, 'generator': 'fixtures.py (real price_chart_reader over FakeStore/FakeAdmission)',
                'saved_arrays_sha256': SAVED['provenance']['source_sha256'], 'states': {}, 'files': {}}

    def write(name, data):
        text = json.dumps(data, indent=1, sort_keys=True)
        (OUT / name).write_text(text, encoding='utf-8')
        manifest['files'][name] = hashlib.sha256(text.encode('utf-8')).hexdigest()

    for name, state in states().items():
        payload = state['payload']
        dates = payload['window']['session_dates']
        label = lambda d: f"{dt.date.fromisoformat(d):%a} {dt.date.fromisoformat(d).day} {dt.date.fromisoformat(d):%b}"
        manifest['states'][name] = {
            'ticker': state['ticker'], 'span': state['span'], 'answered_at': c.iso_z(state['now']),
            'description': state['description'], 'file': f'price-{name}.json',
            'sessions_label': label(dates[0]) if len(dates) == 1 else f'{label(dates[0])} – {label(dates[-1])}',
            'partial': payload['window']['partial'], 'acquisition': payload['acquisition']['state'],
            'price_kind': (payload['price'] or {}).get('kind'),
            'points': len((payload['price'] or {}).get('points', [])),
            'slots': len(payload['chatter']['slots']), 'warnings': len(payload['warnings']),
        }
        write(f'price-{name}.json', payload)
    for ticker in COMPANIES:
        for span in ('1D', '1W'):
            write(f'detail-{ticker}-{span}.json', detail(ticker, span))
    write('board.json', board())
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest['states'], indent=1))


if __name__ == '__main__':
    main()
