"""Build the VC1 preview: two board payloads and a standalone hub harness.

The harness is the real built bundle -- `static/radar/dist` as `npm run build`
emitted it -- with an embedded payload in the same envelope the Flask view
uses. That means what the screenshots show is the shipped code, not a storybook
approximation of it.

Two datasets, and they are never mixed:

  real.json     the local development database, which is a copy of production
                data as of 2026-09-01. Real tickers, real counts, real tone.
                It is NOT live production and it is NOT today's window.
  fixture.json  fictional, and every row exists to exercise one edge the
                design contract names. Nothing here is a measurement.

Usage:
    PYTHONPATH=. py -3.12 scratchpad/vc1_preview.py <outdir>
"""
import copy
import datetime as dt
import json
import pathlib
import sys

from app import app as flask_app
from extensions import db
from features.radar import board as board_mod
from features.radar.routes.api import serialize

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'scratchpad/vc1')
# The newest bucket the local copy holds. A window ending here is a window with
# data in it; `now` would produce an empty board and prove nothing.
REAL_NOW = dt.datetime(2026, 9, 1, 18, 15, 0)

DISPOSABLE = ('personal_apps_radar_te1', 'personal_apps_radar_wt')


def real_payload():
    with flask_app.app_context():
        name = db.engine.url.database
        if name not in DISPOSABLE:
            raise SystemExit(f'refusing to read {name}: not a disposable copy')
        built = board_mod.build(['bluesky', 'fourchan', 'reddit'], REAL_NOW,
                                window_hours=24, limit=50)
        payload = serialize(built)
    payload['watching'] = []
    payload['watch_rows'] = []
    return payload


# --- the fixture ------------------------------------------------------------
#
# Fictional. Company names, prices and counts are invented to exercise the
# edges; the SHAPES are the ones the API really produces.

SERIES = [{'hour': f'2026-09-01T{h:02d}:00:00Z', 'count': None if h == 6 else h}
          for h in range(24)]

# 36 scored feeds, which is what production actually reads, with most of them
# silent in the window. That ratio is the whole reason the source column had to
# change: the old cell printed all 36.
SUBS = ['wallstreetbets', 'stocks', 'options', 'pennystocks', 'smallstreetbets',
        'shortsqueeze', 'thetagang', 'investing', 'stockmarket', 'daytrading',
        'valueinvesting', 'securityanalysis', 'dividends', 'algotrading',
        'robinhood', 'weedstocks', 'canadapennystocks', 'biotechplays',
        'spacs', 'wallstreetbetsELITE', 'stonks', 'trakstocks', 'shroomstocks',
        'moonshots', 'pennystockmovers', 'marketpredictors', 'stocksandtrading',
        'realdaytrading', 'swingtrading', 'tickerchat', 'stockstobuy',
        'financialindependence', 'investingforbeginners', 'wallstreetelite']
ALL_FEEDS = ['bluesky', 'fourchan'] + [f'reddit:{sub}' for sub in SUBS]
assert len(ALL_FEEDS) == 36, len(ALL_FEEDS)


def quote(currency='USD', quality='ok', price=12.0):
    return {'price': price, 'currency': currency, 'market': 'us', 'mic': 'XNAS',
            'venue': 'US markets', 'session': 'regular', 'quality': quality,
            'tape_status': 'ok', 'is_fallback': False, 'as_of': None,
            'stale_minutes': None, 'score_eligible': True}


def frow(**over):
    base = {
        'ticker': 'AAA', 'name': 'Alpha Inc', 'segment': 'large',
        'divergence': 0.9, 'mention_z': 4.1, 'mentions': 68, 'expected': 8.1,
        'ratio': 8.4, 'authors': 42, 'text_ratio': 0.91,
        'sources': ALL_FEEDS,
        'activity_sources': ['bluesky', 'reddit:wallstreetbets'],
        'price': 1.84, 'price_move': 0.022, 'direction': 'up',
        'price_status': 'ok', 'quote': quote(price=1.84),
        'baseline_days': 30, 'marks': [],
        'series': SERIES, 'price_series': [None] * 24,
        'normal_per_hour': 2.4,
        'triplet': {'1': 1.1, '4': 8.4, '24': 3.2},
        'tone': {'bullish': 10, 'neutral': 45, 'bearish': 16},
        'clauses': [{'kind': 'ratio', 'text': '8.4× its normal'}],
        'eligible': True,
    }
    base.update(over)
    return base


FIXTURE_ROWS = [
    # A long legal name, several platforms, a mixed tone sample.
    frow(ticker='KSTR',
         name='Kestrel Biotherapeutics Holdings Ltd. — Class A Ordinary Shares',
         activity_sources=['bluesky', 'fourchan', 'reddit:wallstreetbets',
                           'reddit:options'],
         tone={'bullish': 10, 'neutral': 45, 'bearish': 16}),
    # Four subreddits and nothing else: one platform, four feeds. The rejected
    # board rendered this as `Reddit, Reddit, Reddit, Reddit`.
    frow(ticker='NRLN', name='Northline Energy', ratio=3.1, authors=29,
         mentions=74, price=3.12, price_move=-0.006, direction='down',
         quote=quote(price=3.12),
         activity_sources=['reddit:wallstreetbets', 'reddit:options',
                           'reddit:pennystocks', 'reddit:stocks'],
         tone={'bullish': 31, 'neutral': 12, 'bearish': 6}),
    # Two warnings, and the row is allowed to grow for them.
    frow(ticker='ARDR', name='Ardent Robotics', ratio=6.2, authors=9,
         mentions=112, price=0.76, price_move=0.041,
         quote=quote(price=0.76),
         marks=['single-source', 'partial'],
         activity_sources=['reddit:pennystocks'],
         tone={'bullish': 1, 'neutral': 200, 'bearish': 199}),
    # No baseline and no price: two independent kinds of missing.
    frow(ticker='ORBT', name='Orbitra Systems', ratio=None, baseline_days=2,
         authors=7, mentions=17, price=None, price_move=None,
         direction='flat', quote=quote(quality='unavailable', price=None),
         marks=['warming-up'],
         activity_sources=['bluesky'],
         tone={'bullish': 0, 'neutral': 45, 'bearish': 0}),
    # Every feed looked at, none of them talking: a measured empty list.
    frow(ticker='QUIET', name='Quiet Harbour Materials', ratio=1.2, authors=4,
         mentions=6, price=4.44, price_move=0.0, direction='flat',
         quote=quote(price=4.44),
         activity_sources=[],
         tone={'bullish': 0, 'neutral': 0, 'bearish': 0}),
    # A board cached before the field existed. Must read as unavailable, and
    # must NOT fall back to the 36-feed count.
    frow(ticker='OLDCACHE', name='Legacy Payload Corp', ratio=2.0, authors=15,
         mentions=31, price=18.20, price_move=-0.031, direction='down',
         quote=quote(price=18.20), activity_sources=None,
         tone={'bullish': 4, 'neutral': 3, 'bearish': 0}),
    # A euro listing, so the currency path is on screen too.
    frow(ticker='VELA', name='Vela Materials SE', ratio=1.8, authors=23,
         mentions=48, price=4.44, price_move=0.009,
         quote={**quote(currency='EUR', price=4.44), 'market': 'de',
                'mic': 'XETR', 'venue': 'Xetra'},
         activity_sources=['bluesky', 'reddit:stocks'],
         marks=['no-print'],
         tone={'bullish': 9999, 'neutral': 0, 'bearish': 1}),
]
for _row in FIXTURE_ROWS:
    if _row['activity_sources'] is None:
        del _row['activity_sources']


def envelope(payload, rows=None):
    out = copy.deepcopy(payload)
    if rows is not None:
        out['rows'] = rows
    return out


def fixture_payload(real):
    """The fixture rows inside a real payload envelope.

    The envelope -- market, window, session, counts -- comes from the real
    board so nothing about the page's shell is invented either.
    """
    out = envelope(real, [copy.deepcopy(r) for r in FIXTURE_ROWS])
    out['excluded'] = {'too_few_mentions': 3418, 'too_few_voices': 96}
    out['segment_counts'] = {'all': 7, 'large': 3, 'micro': 4}
    # A POPULATED watch list, so the Watching table can be checked at a width
    # where it is a table. An empty one proves nothing about a layout: the
    # Eighth return made exactly that point about the capture that seemed to
    # justify moving its breakpoint.
    watched = [copy.deepcopy(r) for r in FIXTURE_ROWS[:5]]
    watched[-1]['eligible'] = False
    watched[-1]['floor_reason'] = 'too_few_voices'
    out['watching'] = [r['ticker'] for r in watched]
    out['watch_rows'] = watched
    return out


# Fictional, and labelled as such wherever it is shown. It exists so the
# Activity table has rows at the widths its breakpoint has to be checked at;
# the local database records no ingest runs, so its real payload is seven days
# of nulls and every column collapses.
def fixture_activity(days):
    import datetime as _dt
    out = {'generated_at': REAL_NOW.isoformat() + 'Z',
           'from': (REAL_NOW - _dt.timedelta(days=days)).date().isoformat(),
           'to': REAL_NOW.date().isoformat(),
           'recording_started_at': '2026-08-01T00:00:00Z', 'days': []}
    for index in range(days):
        day = (REAL_NOW - _dt.timedelta(days=days - 1 - index)).date()
        quiet = index % 4 == 3
        out['days'].append({
            'date': day.isoformat(),
            'posts_seen': None if quiet else 15729 + index * 811,
            'posts_new': None if quiet else 22 + index,
            'mentions': None if quiet else 3211 + index * 97,
            'buckets_written': None if quiet else 966 + index * 12,
            'completed_runs': 0 if quiet else 96,
            'counted_runs': 0 if quiet else 96,
            'incomplete_runs': 1 if index == 0 else 0,
            'error_runs': 2 if index == 2 else 0,
            # 'partial' and 'unknown' are the ONLY values the endpoint emits:
            # it never claims a day is complete, because successful runs prove
            # cycles ran and not that anything was covered. An earlier version
            # of this fixture invented 'complete', fell through the page's
            # mapping, and captured a screenshot reading "Nothing recorded"
            # above 16,540 fetched posts. A state the API cannot produce is
            # not evidence of anything.
            'completeness': 'unknown' if quiet else 'partial',
        })
    return out


def dense_payload(real):
    """45 rows, which is what the owner's rejected screenshot was showing."""
    rows = []
    for index in range(45):
        template = FIXTURE_ROWS[index % len(FIXTURE_ROWS)]
        row = copy.deepcopy(template)
        row['ticker'] = f'{template["ticker"][:3]}{index:02d}'
        rows.append(row)
    return envelope(fixture_payload(real), rows)


def empty_payload(real):
    out = envelope(real, [])
    out['excluded'] = {'too_few_mentions': 3418}
    return out


HARNESS = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Radar hub — VC1 preview ({label})</title>
<link rel="stylesheet" href="/static/radar/inter.css">
{css}
<style>body {{ margin: 0; font-family: Inter, system-ui, sans-serif; }}</style>
</head>
<body>
<div id="radar-hub-root"></div>
<script type="application/json" id="radar-hub-data">{shell}</script>
<script type="module" src="{js}"></script>
</body>
</html>
"""


def harness(name, payload, label, assets):
    css = '\n'.join(f'<link rel="stylesheet" href="{href}">'
                    for href in assets['css'])
    # Admin true: `is_admin` is a rendering hint the API does not trust,
    # and with it false the Administration page renders only its refusal
    # banner -- a screenshot that proves nothing about the page this
    # correction's shared styling might have broken.
    shell = json.dumps({'board': payload, 'is_admin': True})
    # `</script>` inside embedded JSON would end the block early.
    shell = shell.replace('</', '<\\/')
    text = HARNESS.format(label=label, css=css, js=assets['js'], shell=shell)
    (OUT / f'{name}.html').write_text(text, encoding='utf-8')
    return name


def assets_from_manifest(root):
    manifest = json.loads(
        (root / 'static/radar/dist/.vite/manifest.json').read_text('utf-8'))
    entry = next(v for k, v in manifest.items() if k.endswith('entries/hub.tsx'))
    return {'js': '/static/radar/dist/' + entry['file'],
            'css': ['/static/radar/dist/' + f for f in entry.get('css', [])]}


def side_payloads(real):
    """The other endpoints the hub calls, so the preview is a whole hub.

    Research, Activity and Administration each fetch their own data. Without
    these the preview 404s on three of its six pages, and a preview that only
    works on one page cannot be used to check that the shared styling this
    correction touched did not break the others.
    """
    from features.radar import activity as activity_mod
    from features.radar import detail as detail_mod
    from features.radar import (detail_panel, llm_sentiment, market_data,
                                observations, spend)
    from features.radar.routes.api import serialize_detail

    out = {}
    with flask_app.app_context():
        if db.engine.url.database not in DISPOSABLE:
            raise SystemExit('refusing: not a disposable copy')
        for row in real['rows'][:6]:
            try:
                built = detail_panel.build(
                    row['ticker'], ['bluesky', 'fourchan', 'reddit'], REAL_NOW,
                    window_hours=24, span=detail_mod.DEFAULT_SPAN, market='us')
                out[f'ticker-{row["ticker"]}'] = serialize_detail(built)
            except Exception as exc:                      # noqa: BLE001
                print(f'  detail {row["ticker"]}: {exc}')
        for days in activity_mod.ALLOWED_DAYS:
            out[f'activity-{days}'] = activity_mod.summary(REAL_NOW, days)
        out['ops'] = {
            'generated_at': activity_mod.iso_z(REAL_NOW),
            'spend': spend.summary(),
            'sentiment': llm_sentiment.ops_summary(),
            'market_data': market_data.ops_summary(REAL_NOW),
            'capture': {'latest_observed_at': activity_mod.iso_z(
                observations.latest_observed_at())},
        }
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    root = pathlib.Path(__file__).resolve().parent.parent
    assets = assets_from_manifest(root)

    real = real_payload()
    (OUT / 'real.json').write_text(json.dumps(real), encoding='utf-8')

    side = side_payloads(real)
    api = OUT / 'api'
    api.mkdir(exist_ok=True)
    for name, payload in side.items():
        (api / f'{name}.json').write_text(json.dumps(payload, default=str),
                                          encoding='utf-8')
    # Dataset-specific answers win over the shared ones. The fixture page gets
    # fictional activity; the real page keeps the real, mostly-null one.
    for days in (1, 7, 30):
        (api / f'fixture-activity-{days}.json').write_text(
            json.dumps(fixture_activity(days)), encoding='utf-8')
        (api / f'dense-activity-{days}.json').write_text(
            json.dumps(fixture_activity(days)), encoding='utf-8')
    print(f'side payloads: {", ".join(sorted(side))} (+ fixture activity)')

    pages = {
        'real': (real, 'REAL local dev data, 24h window ending 2026-09-01 18:15'),
        'fixture': (fixture_payload(real), 'FICTIONAL fixture'),
        'dense': (dense_payload(real), 'FICTIONAL fixture, 45 rows'),
        'empty': (empty_payload(real), 'FICTIONAL fixture, empty board'),
    }
    for name, (payload, label) in pages.items():
        harness(name, payload, label, assets)

    print(f'rows: real={len(real["rows"])} '
          f'fixture={len(pages["fixture"][0]["rows"])} '
          f'dense={len(pages["dense"][0]["rows"])}')
    print(f'assets: {assets}')
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
