"""The fix wave's two client-honesty items, in a real browser at 390x844.

Two things the whole-branch review returned, both only visible on a page that
opens on a waiting shell:

  focus   a board arriving after a wait auto-selects the top row, and the
          panel took focus -- measured in the ledger's browser check, run 3, as
          4,219 px of scroll away from the list the reader was watching. The
          reader's own click must still move focus.
  copy    while a board is pending the detail pane said "Nothing on the board
          to look at." and the view tabs read "All 0 · Discover 0 · …" --
          absence rendered as a measured zero.

Deliberately NO database and NO producer. What is under test is the built
client bundle, so this serves the real `templates/radar/board.html` shell, the
real `static/radar/` assets and the real `static/radar/dist/` build, with the
board API stubbed: the first answer is `board_shared._waiting`'s shell, every
later one is a ready board of fifty rows. That is the exact sequence the
ledger's run 3 measured, without `personal_apps_radar_perf3_scale`, the
producer, or a session cookie -- none of which this page's focus depends on.

    cd personal_apps
    <python 3.12> scratchpad/perf3/browser_focus_check.py [--port 5091]

Prints one JSON object: the three moments the ledger measured (pending, rows
arrived, after the panel's detail loads), the reader's own click, and what the
pending shell says where its numbers would be.
"""
import argparse
import contextlib
import http.server
import json
import pathlib
import random
import socketserver
import threading
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
APP_DIR = HERE.parents[1]
STATIC = APP_DIR / 'static'

ROWS = 50
STAMP = '2026-08-22T19:00:00Z'


def quote():
    return {
        'market': 'us', 'venue': 'Nasdaq', 'mic': 'XNAS', 'currency': 'USD',
        'price': 10, 'regular_move': 0.012, 'extended_move': None,
        'session': 'regular', 'quality': 'live', 'age_seconds': 0,
        'quoted_at': STAMP, 'tape_status': 'ok', 'score_eligible': True,
        'score_term': 'divergence', 'is_fallback': False, 'source': 'legacy',
        'price_basis': 'trade', 'bid': None, 'ask': None,
    }


def row(ticker, at):
    rnd = random.Random(ticker)
    return {
        'ticker': ticker, 'name': f'{ticker} Industries', 'segment': 'large',
        'divergence': 2.5 - at * 0.03, 'mention_z': 3.2, 'mentions': 40 - at,
        'expected': 6, 'ratio': 3.0, 'authors': 9, 'text_ratio': 0.9,
        'sources': ['bluesky'], 'activity_sources': ['bluesky'],
        'price': 10, 'price_move': 0.012, 'direction': 'up',
        'price_status': 'ok', 'baseline_days': 30, 'marks': [],
        'series': [{'hour': f'h{i}', 'count': rnd.randint(0, 9)}
                   for i in range(25)],
        'price_series': [None] * 25,
        'normal_per_hour': None,
        'triplet': {'1': 1.1, '4': 3.2, '24': 2.0},
        'tone': {'bullish': 4, 'neutral': 10, 'bearish': 2},
        'clauses': [{'kind': 'ratio', 'text': '3x its normal'},
                    {'kind': 'venues', 'text': '2 venues'}],
        'eligible': True, 'quote': quote(),
    }


def echo():
    """`board_shared._selection_echo`: the question, without the answer."""
    return {
        'market': 'us', 'display_timezone': 'Europe/Berlin',
        'market_venue': 'US markets', 'session': 'regular',
        'next_boundary_label': 'closes', 'next_boundary_at': STAMP,
        'sources': ['bluesky', 'fourchan', 'reddit'],
        'all_sources': ['bluesky', 'fourchan', 'reddit'],
        'segments': [], 'min_venues': 1, 'window_hours': 4,
        'sort': None, 'dir': 'desc',
        'triplet_hours': [1, 4, 24], 'series_hours': 24, 'lead_count': 3,
        'segment_counts': {}, 'venue_counts': {'any': 0, 'multi': 0},
        'excluded': {},
    }


def waiting():
    shell = echo()
    shell.update({
        'shared': True, 'pending': True, 'busy': False, 'stale': False,
        'failed': False, 'generated_at': None, 'as_of': None,
        'built_at': None, 'age_seconds': None, 'fresh_seconds': 120,
        'hard_expiry_seconds': 600, 'retry_after_ms': 1000,
        'queue_age_seconds': 0, 'ops_collected_at': None, 'rows': None,
        'watching': [], 'watch_rows': [],
    })
    return shell


def ready():
    board = echo()
    rows = [row(f'T{at:02d}', at) for at in range(ROWS)]
    board.update({
        'shared': True, 'pending': False, 'busy': False, 'stale': False,
        'failed': False, 'generated_at': STAMP, 'as_of': STAMP,
        'built_at': STAMP, 'age_seconds': 0, 'fresh_seconds': 120,
        'hard_expiry_seconds': 600, 'retry_after_ms': None,
        'queue_age_seconds': None, 'ops_collected_at': STAMP,
        'rows': rows, 'watching': [], 'watch_rows': [],
        'segment_counts': {'all': ROWS, 'large': ROWS},
        'venue_counts': {'any': ROWS, 'multi': 2},
    })
    return board


def detail(ticker):
    return {
        'market': 'us', 'display_timezone': 'Europe/Berlin',
        'identity': {
            'ticker': ticker, 'name': f'{ticker} Industries',
            'exchange': 'NASDAQ', 'segment': 'large', 'market_cap': 1e9,
            'ipo_date': '2020-01-01', 'price': 10, 'price_move': 0.012,
            'price_status': 'ok', 'session': 'regular', 'quote': quote(),
        },
        'read': [{'kind': 'plain', 'text': f'{ticker} is being discussed.'}],
        'chart': {
            'from': '2025-08-23T00:00:00Z', 'span': '1Y',
            'step_minutes': 1440,
            'closes': [100 + i for i in range(365)],
            'chatter': [None if i < 360 else i for i in range(365)],
            'sessions': [], 'currency': None, 'basis_venue': None,
            'converted_from': None, 'priced_from': 'daily',
            'normal_per_slot': None, 'watched_from': '2026-08-18',
        },
        'breakdown': {
            'venues': [{'source': 'bluesky', 'mentions': 20, 'voices': 9}],
            'bullish': 4, 'neutral': 10, 'bearish': 2, 'disagreements': 1,
            'top_author_share': 0.2, 'top_two_share': 0.3,
            'peak_hour': '2026-08-22T14:00:00Z', 'peak_count': 9,
            'first_seen': '2026-08-18', 'mentions': 20, 'voices': 9,
        },
        'posts': [], 'post_total': 0,
    }


def bundle():
    """The built entry for the board island, from vite's own manifest."""
    manifest = json.loads(
        (STATIC / 'radar/dist/.vite/manifest.json').read_text('utf-8'))
    return '/static/radar/dist/' + manifest[
        'static/radar/src/entries/board.tsx']['file']


def shell_html():
    """templates/radar/board.html with the Jinja calls resolved by hand.

    Only the three `url_for`/`vite_asset` calls and the payload differ; the
    markup, the ids the island mounts on and the stylesheets are the file's.
    """
    template = (APP_DIR / 'templates/radar/board.html').read_text('utf-8')
    body = template.split('<body>', 1)[1].split('</body>', 1)[0]
    body = body.replace(
        '{{ payload | tojson }}',
        json.dumps(waiting()).replace('<', '\\u003c').replace('&', '\\u0026'))
    body = body.replace(
        "{{ vite_asset('board', feature='radar') }}", bundle())
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Radar</title>
  <meta name="csrf-token" content="focus-check">
  <link rel="stylesheet" href="/static/radar/inter.css">
  <link rel="stylesheet" href="/static/radar/radar.css">
</head>
<body>
{body}
</body>
</html>"""


class Handler(http.server.SimpleHTTPRequestHandler):
    """The shell, the real static assets, and a stubbed board API."""

    boards = 0
    lock = threading.Lock()

    def do_GET(self):                       # noqa: N802 - stdlib's spelling
        path = urllib.parse.urlparse(self.path).path
        if path in ('/radar/', '/radar'):
            return self.send(shell_html().encode('utf-8'), 'text/html')
        if path == '/radar/api/board':
            with Handler.lock:
                Handler.boards += 1
                first = Handler.boards == 1
            return self.json(waiting() if first else ready())
        if path.startswith('/radar/api/ticker/'):
            return self.json(detail(path.rsplit('/', 1)[-1]))
        if path.startswith('/static/'):
            return self.file(path[len('/static/'):])
        self.send_error(404)

    def json(self, body):
        self.send(json.dumps(body).encode('utf-8'), 'application/json')

    def file(self, relative):
        target = (STATIC / relative).resolve()
        if not str(target).startswith(str(STATIC.resolve())):
            return self.send_error(403)
        if not target.is_file():
            return self.send_error(404)
        types = {'.js': 'text/javascript', '.css': 'text/css',
                 '.woff2': 'font/woff2', '.svg': 'image/svg+xml',
                 '.json': 'application/json'}
        self.send(target.read_bytes(),
                  types.get(target.suffix, 'application/octet-stream'))

    def send(self, body, content_type):
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


READING = """() => {
  const panel = document.querySelector('main.detail')
  const active = document.activeElement
  const box = panel ? panel.getBoundingClientRect() : null
  return {
    scrollY: Math.round(window.scrollY),
    focus: active ? (active.tagName.toLowerCase()
      + (active.className ? '.' + String(active.className).split(' ')[0] : ''))
      : null,
    panelTop: box ? Math.round(box.top + window.scrollY) : null,
    rows: document.querySelectorAll('.row').length,
    panelText: panel ? panel.textContent.slice(0, 80) : null,
    views: (() => {
      const strip = document.querySelector('.tabs.views')
      return strip ? strip.textContent.replace(/\\s+/g, ' ').trim() : null
    })(),
    uncounted: document.querySelectorAll(
      '.tabs.views [aria-label="not calculated yet"]').length,
  }
}"""


def measure(port):
    from playwright.sync_api import sync_playwright

    out = {}
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={'width': 390, 'height': 844})
        page.goto(f'http://127.0.0.1:{port}/radar/',
                  wait_until='networkidle')
        page.wait_for_selector('.none.pending')
        out['pending'] = page.evaluate(READING)

        # The wait's first poll lands at ~1 s and brings the board.
        page.wait_for_selector('.row', timeout=10_000)
        page.wait_for_timeout(200)
        out['rows_arrived'] = page.evaluate(READING)

        # The panel's own request answers next; the ledger's run 3 measured
        # the jump 3.5 s after the rows.
        page.wait_for_timeout(4000)
        out['detail_loaded'] = page.evaluate(READING)

        # And the reader's own pick must still move focus.
        page.evaluate('window.scrollTo(0, 0)')
        page.wait_for_timeout(100)
        page.locator('.row').nth(2).click()
        page.wait_for_timeout(2500)
        out['reader_clicked'] = page.evaluate(READING)
        browser.close()
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5091)
    args = parser.parse_args()

    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.ThreadingTCPServer(('127.0.0.1', args.port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        print(json.dumps(measure(args.port), indent=2))
    finally:
        with contextlib.suppress(Exception):
            server.shutdown()


if __name__ == '__main__':
    main()
