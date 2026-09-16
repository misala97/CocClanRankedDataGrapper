"""MD-SELECTED-PRICE-ALPACA-C1 browser fixtures -- SYNTHETIC ENVELOPES, REAL SHAPES.

    py -3.12 radar-design/artifacts/md-selected-price-alpaca-c1/browser/fixtures.py

Every price-chart answer is the REAL reader/contract output
(features.radar.price_chart_reader.build_response over the unit suite's fake
store and fake admission) for a series the REAL adapter normalized
(price_chart_contract.normalize_alpaca) from an Alpaca-shaped payload.

Where the prices come from:

- FT's 64 reported regular minutes plus its 20:00:00Z closing bar are the
  actual closes the accepted area preview was drawn from
  (artifacts/md-selected-price-personal-preview/1D-raw.json, two single-attempt
  owner-approved Yahoo requests on 2026-09-16), rewritten into Alpaca's bar
  shape: a minute nobody reported is simply ABSENT, which is exactly what
  Alpaca does.
- AAPL's dense 1D and 1W closes are the saved research arrays
  (tests/selected_price_unit/fixtures/yahoo_saved_arrays.json, 2026-09-15),
  rewritten the same way.

Nothing here contacts Alpaca, any other provider, a database or production,
and no credential is read: normalization needs none. Chatter, tone, quotes,
closes, detail and board payloads are synthetic.
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
PREVIEW = ROOT / 'radar-design' / 'artifacts' / 'md-selected-price-personal-preview'
SAVED = json.loads((PERSONAL / 'tests' / 'selected_price_unit' / 'fixtures'
                    / 'yahoo_saved_arrays.json').read_text(encoding='utf-8'))
SOURCES = ['bluesky', 'fourchan', 'reddit:wallstreetbets']
QUARTER = dt.timedelta(minutes=15)


def utc(*parts):
    return dt.datetime(*parts, tzinfo=UTC)


def naive(when):
    return when.astimezone(UTC).replace(tzinfo=None)


COMPANIES = {
    'FT': dict(name='Franklin Universal Trust', venue='New York Stock Exchange', mic='XNYS', price=7.39),
    'AAPL': dict(name='Apple Inc', venue='NASDAQ', mic='XNMS', price=330.46),
    'MSFT': dict(name='Microsoft Corp', venue='NASDAQ', mic='XNGS', price=431.18),
    'NVDA': dict(name='NVIDIA Corp', venue='NASDAQ', mic='XNMS', price=121.07),
}


def preview_closes(name):
    """(epoch, close) pairs for the reported minutes only, from the accepted
    preview's saved raw response."""
    result = json.loads((PREVIEW / name).read_text(encoding='utf-8'))['chart']['result'][0]
    closes = result['indicators']['quote'][0]['close']
    return [(stamp, close) for stamp, close in zip(result['timestamp'], closes) if close is not None]


def saved_closes(key):
    saved = SAVED['series'][key]
    return [(stamp, close) for stamp, close in zip(saved['timestamp'], saved['close'])
            if close is not None]


def alpaca_payload(pairs, symbol):
    """Alpaca's own envelope: one bars key, bar START timestamps in RFC-3339,
    a positive close per bar, and nothing at all for an unreported minute."""
    bars = [{'t': c.iso_z(dt.datetime.fromtimestamp(stamp, UTC)), 'o': close, 'h': close,
             'l': close, 'c': close, 'v': 100, 'n': 4, 'vw': close}
            for stamp, close in pairs]
    return {'bars': {symbol: bars}, 'next_page_token': None}


def alpaca_series(pairs, ticker, window, received, now):
    info = COMPANIES[ticker]
    identity = {'provider_symbol': ticker, 'currency': 'USD', 'mic': info['mic']}
    spec, refusal = c.alpaca_request_spec(identity, window, now=now)
    assert refusal is None, refusal
    result = c.normalize_alpaca(alpaca_payload(pairs, ticker), spec, received_at=received.timestamp())
    assert result['kind'] == 'ok', result
    return result, spec


def buckets_for(window, *, seed=0, quiet=(), missing=(), truncated=(), config_switch=None,
                overlap_at=None):
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
                     instruments=[instrument_row(ticker=ticker, provider_symbol=ticker,
                                                 mic=info['mic'], venue=info['venue'])], **store)
    reader.clear_local_cache()
    payload = reader.build_response(ticker, SOURCES, span, now, coordinator=FakeAdmission(admission),
                                    store=fake)
    assert len(fake.calls) <= 8
    return payload


def answer(state, retry=None, reason=None, series=None):
    return {'state': state, 'retry_after_seconds': retry, 'reason': reason, 'series': series}


def segments_of(payload):
    """The hard segments the renderer will draw, so the manifest states what
    each screenshot must show."""
    points = [p for p in (payload['price'] or {}).get('points', []) if p['value'] is not None]
    runs = []
    for point in points:
        if runs and runs[-1]['key'] == point['segment']:
            runs[-1]['points'] += 1
        else:
            runs.append({'key': point['segment'], 'points': 1})
    return runs


def states():
    out = {}

    # 1) FT's real sparse session, through the Alpaca adapter. The closing-minute
    # bar at 20:00:00Z is inside the 1D extended window, so the ruling makes it
    # a SEPARATE after-hours segment rather than part of the regular line.
    now = utc(2026, 9, 16, 0, 34)
    window = c.window_for('1D', now)
    series, _ = alpaca_series(preview_closes('1D-raw.json'), 'FT', window, now, now)
    rows = buckets_for(window, seed=1, quiet=[(naive(utc(2026, 9, 15, 8)), naive(utc(2026, 9, 15, 13)))])
    out['sparse_1d'] = dict(ticker='FT', span='1D', now=now, description=(
        "1D ready, Alpaca consolidated SIP: FT's 64 actual reported regular minutes plus its "
        '20:00:00Z closing bar as a separate after-hours segment'),
        payload=build('FT', '1D', now, answer('ready', series=series), buckets=rows,
                      tone=tone_for(rows, now)))

    # 2) A liquid session: dense actual observations, same renderer.
    now = utc(2026, 9, 15, 13, 50, 21)
    window = c.window_for('1D', now)
    series, _ = alpaca_series(saved_closes('yahoo_1d_1m_AAPL'), 'AAPL', window, now, now)
    rows = buckets_for(window, seed=2, truncated={naive(utc(2026, 9, 15, 12, 15))},
                       overlap_at=naive(utc(2026, 9, 15, 11, 0)))
    out['dense_1d'] = dict(ticker='AAPL', span='1D', now=now, description=(
        '1D ready, current session so far: dense AAPL minutes across pre-market and the regular '
        'open, a truncated bucket and a Reddit overlap'),
        payload=build('AAPL', '1D', now, answer('ready', series=series), buckets=rows,
                      tone=tone_for(rows, now)))

    # 3) 1W five-minute bars: five regular sessions, five segments, no
    # overnight line and no fill across a night.
    now = utc(2026, 9, 15, 13, 50, 19)
    window = c.window_for('1W', now)
    series, _ = alpaca_series(saved_closes('yahoo_5d_5m_AAPL'), 'AAPL', window, now, now)
    rows = buckets_for(window, seed=3, missing={naive(utc(2026, 9, 11, 15, 0))})
    out['week_1w'] = dict(ticker='AAPL', span='1W', now=now, description=(
        '1W ready, Alpaca five-minute bars over five modeled regular sessions: one filled segment '
        'per session, nothing drawn across a night'),
        payload=build('AAPL', '1W', now, answer('ready', series=series), buckets=rows,
                      tone=tone_for(rows, now)))

    # 4) The delayed feed does not reach this window yet: one whole stored
    # quote series, labelled as the fallback it is.
    now = utc(2026, 9, 15, 15, 12)
    window = c.window_for('1D', now)
    rows = buckets_for(window, seed=4)
    out['fallback_1d'] = dict(ticker='MSFT', span='1D', now=now, description=(
        '1D Alpaca unavailable (delayed data does not reach this window yet): stored Finnhub quotes '
        'of the same XNGS instrument as the coherent fallback, with a 90-minute gap'),
        payload=build('MSFT', '1D', now,
                      answer('unavailable', None, 'delayed provider data does not reach this window yet'),
                      buckets=rows, tone=tone_for(rows, now),
                      quotes=quotes_for(window, 'XNGS', start_price=429.4,
                                        gap=(naive(utc(2026, 9, 15, 11)), naive(utc(2026, 9, 15, 12, 30))))))

    # 5) Nothing to show at all, said plainly, with chatter still readable.
    window = c.window_for('1W', now)
    rows = buckets_for(window, seed=5,
                       quiet=[(naive(utc(2026, 9, 10, 0)), naive(utc(2026, 9, 11, 12)))])
    out['unavailable_1w'] = dict(ticker='NVDA', span='1W', now=now, description=(
        "1W provider refused the credentials (backoff 60 s) and nothing is stored in the window: "
        'price null with its reason; a day and a half of unknown chatter'),
        payload=build('NVDA', '1W', now,
                      answer('backoff', 60, "the provider refused this process's credentials"),
                      buckets=rows, tone=tone_for(rows, now)))

    # 6) Real chatter states beside a real price line: unknown, partial, zero.
    now = utc(2026, 9, 16, 0, 34)
    window = c.window_for('1D', now)
    series, _ = alpaca_series(preview_closes('1D-raw.json'), 'FT', window, now, now)
    rows = buckets_for(window, seed=6,
                       quiet=[(naive(utc(2026, 9, 15, 14)), naive(utc(2026, 9, 15, 16)))],
                       missing={naive(utc(2026, 9, 15, 17, 0))},
                       truncated={naive(utc(2026, 9, 15, 18, 15))},
                       config_switch=naive(utc(2026, 9, 15, 19, 0)),
                       overlap_at=naive(utc(2026, 9, 15, 19, 30)))
    out['chatter_gaps'] = dict(ticker='FT', span='1D', now=now, description=(
        'The same FT session with two hours of unknown chatter, a missing bucket, a truncated '
        'bucket, a source-configuration change and a Reddit overlap'),
        payload=build('FT', '1D', now, answer('ready', series=series), buckets=rows,
                      tone=tone_for(rows, now)))
    return out


def quote(ticker):
    info = COMPANIES[ticker]
    return {'market': 'us', 'venue': 'NYSE' if ticker == 'FT' else info['venue'], 'mic': info['mic'],
            'currency': 'USD', 'price': info['price'], 'regular_move': 0.0123, 'extended_move': None,
            'session': 'regular', 'quality': 'delayed', 'age_seconds': 900,
            'quoted_at': '2026-09-15T19:55:00Z', 'tape_status': 'ok', 'score_eligible': True,
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
        'generated_at': '2026-09-15T20:00:00Z', 'market': 'us', 'display_timezone': 'Europe/Berlin',
        'market_venue': 'US markets', 'next_boundary_label': 'opens',
        'next_boundary_at': '2026-09-16T13:30:00Z', 'sources': ['bluesky', 'fourchan', 'reddit'],
        'all_sources': ['bluesky', 'fourchan', 'reddit'], 'segments': [], 'session': 'closed',
        'window_hours': 4, 'min_venues': 1, 'venue_counts': {'any': 4, 'multi': 3}, 'sort': None,
        'dir': 'desc', 'segment_counts': {'all': 4, 'large': 4}, 'triplet_hours': [1, 4, 24],
        'series_hours': 24, 'lead_count': 3,
        'rows': [row(t, i) for i, t in enumerate(COMPANIES)], 'excluded': {}, 'watching': [],
        'watch_rows': [], 'shared': False, 'pending': False, 'busy': False, 'stale': False,
        'failed': False, 'as_of': '2026-09-15T20:00:00Z', 'built_at': '2026-09-15T20:00:00Z',
        'age_seconds': 0, 'fresh_seconds': 120, 'hard_expiry_seconds': 600, 'retry_after_ms': None,
        'queue_age_seconds': None, 'ops_collected_at': '2026-09-15T20:00:00Z',
    }


def detail(ticker, span):
    info = COMPANIES[ticker]
    slots, step = (96, 15) if span == '1D' else (168, 60)
    start = utc(2026, 9, 15, 20, 0) - dt.timedelta(minutes=slots * step)
    return {
        'market': 'us', 'display_timezone': 'Europe/Berlin',
        'identity': {'ticker': ticker, 'name': info['name'],
                     'exchange': 'NYSE' if ticker == 'FT' else info['venue'],
                     'segment': 'large', 'market_cap': 2.9e11, 'ipo_date': '1988-09-23',
                     'price': info['price'], 'price_move': 0.0123, 'price_status': 'ok',
                     'session': 'closed', 'quote': quote(ticker)},
        'read': [{'kind': 'plain', 'text': f'{ticker} is being discussed more than usual.'}],
        'chart': {'from': c.iso_z(start), 'span': span, 'step_minutes': step,
                  'closes': [round(info['price'] - 0.2 + (i % 7) * 0.04, 2) if i % 5 else None
                             for i in range(slots)],
                  'chatter': [(i * 3) % 7 for i in range(slots)], 'sessions': [], 'currency': 'USD',
                  'basis_venue': None, 'converted_from': None, 'priced_from': 'intraday',
                  'normal_per_slot': None, 'watched_from': '2026-08-01'},
        'breakdown': {'venues': [{'source': 'bluesky', 'mentions': 20, 'voices': 9},
                                 {'source': 'reddit', 'mentions': 18, 'voices': 11}],
                      'bullish': 12, 'neutral': 20, 'bearish': 6, 'disagreements': 2,
                      'top_author_share': 0.18, 'top_two_share': 0.3, 'peak_hour': '2026-09-15T19:00:00Z',
                      'peak_count': 9, 'first_seen': '2026-08-01', 'mentions': 38, 'voices': 20},
        'posts': [], 'post_total': 0,
    }


def main():
    OUT.mkdir(exist_ok=True)
    manifest = {'synthetic_envelopes': True, 'live_provider_requests': 0,
                'generator': 'fixtures.py (real normalize_alpaca + price_chart_reader over FakeStore)',
                'saved_arrays_sha256': SAVED['provenance']['source_sha256'],
                'ft_closes_from': 'radar-design/artifacts/md-selected-price-personal-preview/1D-raw.json',
                'states': {}, 'files': {}}

    def write(name, data):
        text = json.dumps(data, indent=1, sort_keys=True)
        (OUT / name).write_text(text, encoding='utf-8')
        manifest['files'][name] = hashlib.sha256(text.encode('utf-8')).hexdigest()

    def label(day):
        parsed = dt.date.fromisoformat(day)
        return f'{parsed:%a} {parsed.day} {parsed:%b}'

    for name, state in states().items():
        payload = state['payload']
        dates = payload['window']['session_dates']
        price = payload['price'] or {}
        segments = segments_of(payload)
        manifest['states'][name] = {
            'ticker': state['ticker'], 'span': state['span'], 'answered_at': c.iso_z(state['now']),
            'description': state['description'], 'file': f'price-{name}.json',
            'sessions_label': label(dates[0]) if len(dates) == 1 else f'{label(dates[0])} – {label(dates[-1])}',
            'partial': payload['window']['partial'], 'acquisition': payload['acquisition']['state'],
            'price_source': price.get('source'), 'price_kind': price.get('kind'),
            'observations': price.get('observations'), 'expected_intervals': price.get('expected_intervals'),
            'segments': segments,
            'multi_point_segments': sum(1 for s in segments if s['points'] > 1),
            'single_point_segments': sum(1 for s in segments if s['points'] == 1),
            'slots': len(payload['chatter']['slots']),
            'unknown_slots': sum(1 for s in payload['chatter']['slots'] if s['count'] is None),
            'partial_slots': sum(1 for s in payload['chatter']['slots'] if s['coverage'] == 'partial'),
            'zero_slots': sum(1 for s in payload['chatter']['slots'] if s['count'] == 0),
            'warnings': len(payload['warnings']),
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
