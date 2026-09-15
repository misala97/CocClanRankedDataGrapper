"""MD-SELECTED-PRICE-CORRECTION-1: one bounded built-hub browser check of the
CHANGED behaviour only (python-playwright, Chromium).

    py -3.12 -u radar-design/artifacts/md-selected-price-correction-1/browser/verify_correction.py

FIXTURE evidence, not database, provider or production QA:
- Serves ONLY candidate files from a thread in this process on 127.0.0.1:5047
  (refuses if anything answers there first): the real templates/radar/hub.html
  with a synthetic shell, and the freshly built static/radar/dist bundle.
- Every /radar/api/* request is answered by page.route. Chart answers reuse the
  implementation's saved fixtures READ-ONLY
  (../../md-selected-price-implementation/browser/fixtures/); a failure is a
  503 store_unavailable.
- 1440x1000 and 390x844 (touch), Research and the Human Chatter research
  panel: initial failure; an answered live-session chart whose refresh fails
  (the old chart and its now/current-session wording must disappear); and
  recovery through Retry. Admin: Unknown workers / coordinator not started,
  and a positive WEB_CONCURRENCY / coordinator started.

Writes results.json and screenshots/ beside this file; exits 1 on any failed
check. The screenshots must then be VIEWED.
"""
import json
import mimetypes
import re
import socket
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import jinja2
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PERSONAL = ROOT / 'personal_apps'
STATIC = (PERSONAL / 'static').resolve()
FIX = ROOT / 'radar-design/artifacts/md-selected-price-implementation/browser/fixtures'
SHOTS = HERE / 'screenshots'
PORT = 5047
BASE = f'http://127.0.0.1:{PORT}'
DIST_MANIFEST = json.loads((STATIC / 'radar/dist/.vite/manifest.json').read_text(encoding='utf-8'))
HUB_ENTRY = DIST_MANIFEST['static/radar/src/entries/hub.tsx']
SERVER_LOG = []


def load(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


def now_z():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def board(sort=None, direction='desc'):
    payload = load('board.json')
    stamp = now_z()
    payload.update(generated_at=stamp, as_of=stamp, built_at=stamp, ops_collected_at=stamp,
                   sort=sort, dir=direction)
    return payload


def ops_payload(selected):
    return {
        'generated_at': now_z(),
        'spend': {'today_usd': 0, 'month_usd': 1.25, 'unpriced_tokens': 501000},
        'sentiment': {'pending': 12, 'gated_pending': 4, 'p95_age_minutes': 31,
                      'review': {'demanded': 5, 'attempted': 5, 'served': 4, 'capped': 1, 'over_ceiling': 0}},
        'market_data': {
            'cycles': {}, 'mapping_generations': {'active': 1}, 'quote_basis_24h': {'trade': 900},
            'grouped_closes': {'latest_accepted_date': '2026-09-14', 'retryable_gaps': [],
                               'counts': {'provider_rows': 9000, 'written': 8800},
                               'error_code': None, 'http_status': None, 'backoff_until': None},
            'post_close_claims': {}, 'de_download_budget_24h': {'spent': 4, 'limit': 40, 'remaining': 36}},
        'capture': {'latest_observed_at': None},
        'board_results': {},
        'selected_price_ops': selected,
    }


def selected_ops(*, workers, started):
    return {
        'scope': 'process', 'pid': 31337, 'coordinator_started_at': started,
        'charts_enabled': True, 'yahoo_enabled': False,
        'configured_web_workers': workers, 'configured_web_workers_source': 'WEB_CONCURRENCY',
        'limits': {'max_children': 1, 'starts_per_60s': 10, 'deadline_seconds': 6.0,
                   'cache_keys': 128, 'cache_bytes': 8388608},
        'note': ('Counts for this web process only, reset when it restarts. Each web worker has its own '
                 "limits; the ingest daemon's Yahoo traffic is separate."),
        'in_flight': False, 'in_flight_seconds': None, 'cache_keys': 0, 'cache_bytes': 0,
        'rolling_starts_60s': 0, 'backoff_until': None, 'quarantined': False,
        'counters': {'success': 3, 'timeout': 1}, 'latency': {'count': 4, 'sum_seconds': 3.1, 'max_seconds': 1.2},
    }


ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(str(PERSONAL / 'templates')),
                         autoescape=jinja2.select_autoescape(['html']))
ENV.globals.update(
    url_for=lambda endpoint, filename: f'/static/{filename}',
    csrf_token=lambda: 'qa-local-token',
    vite_asset=lambda name, feature: f"/static/radar/dist/{HUB_ENTRY['file']}",
    vite_asset_css=lambda name, feature: [f'/static/radar/dist/{css}' for css in HUB_ENTRY.get('css', [])],
)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path in ('/radar/', '/radar/hub/'):
            html = ENV.get_template('radar/hub.html').render(
                shell={'board': board(), 'is_admin': True, 'selected_price_charts_enabled': True})
            return self._send(200, html.encode('utf-8'), 'text/html; charset=utf-8')
        if parts.path.startswith('/static/'):
            target = (STATIC / unquote(parts.path[len('/static/'):])).resolve()
            if STATIC in target.parents and target.is_file():
                return self._send(200, target.read_bytes(),
                                  mimetypes.guess_type(str(target))[0] or 'application/octet-stream')
        if parts.path != '/favicon.ico':
            SERVER_LOG.append(parts.path)
        return self._send(404, b'not here', 'text/plain')

    def _send(self, status, body, kind):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass


def port_is_free():
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex(('127.0.0.1', PORT)) != 0


class Mocks:
    """`chart` is 'ok' (the saved fixture) or 'fail' (503); `ops` is a payload."""

    def __init__(self, page, chart_file='price-stale.json', chart='ok', ops=None):
        self.chart_file, self.chart, self.ops = chart_file, chart, ops
        self.chart_requests = []
        self.unexpected = []
        page.route('**/radar/api/**', self.handle)

    def handle(self, route):
        url = urlsplit(route.request.url)
        query = parse_qs(url.query, keep_blank_values=True)
        path = url.path
        if path == '/radar/api/board':
            return route.fulfill(json=board(query.get('sort', [None])[0], query.get('dir', ['desc'])[0]))
        if path == '/radar/api/search':
            return route.fulfill(json={'matches': []})
        if path == '/radar/api/ops' and self.ops is not None:
            return route.fulfill(json=self.ops)
        if re.fullmatch(r'/radar/api/ticker/AAPL/price-chart', path):
            self.chart_requests.append({'mode': self.chart, 'at': time.time()})
            if self.chart == 'fail':
                return route.fulfill(status=503, json={'code': 'store_unavailable',
                                                        'error': 'the store could not be read'})
            return route.fulfill(json=load(self.chart_file))
        detail = re.fullmatch(r'/radar/api/ticker/([^/]+)', path)
        if detail:
            file = FIX / f"detail-{unquote(detail.group(1))}-{query.get('span', ['1D'])[0]}.json"
            if file.exists():
                return route.fulfill(json=load(file.name))
        self.unexpected.append(route.request.url)
        return route.fulfill(status=404, json={'error': 'unmocked'})


RESULTS = {'fixture_evidence': True, 'port': PORT, 'dist_hub': HUB_ENTRY['file'],
           'dist_css': HUB_ENTRY.get('css'), 'cases': {}, 'failures': [], 'server_404': SERVER_LOG}


class Case:
    def __init__(self, label):
        self.label = label
        self.facts = {'checks': {}}
        RESULTS['cases'][label] = self.facts

    def check(self, name, ok, detail=None):
        self.facts['checks'][name] = bool(ok)
        if detail is not None:
            self.facts.setdefault('details', {})[name] = detail
        if not ok:
            RESULTS['failures'].append(f'{self.label}: {name}' + (f' -- {detail}' if detail is not None else ''))


def chart_section(page):
    return page.locator('section.rh-panel').filter(has=page.locator('.rh-spans')).first


def shoot(locator, name):
    SHOTS.mkdir(exist_ok=True)
    locator.scroll_into_view_if_needed()
    locator.page.wait_for_timeout(300)
    locator.screenshot(path=str(SHOTS / f'{name}.png'))
    return f'{name}.png'


def no_overflow(page, case):
    metrics = page.evaluate('({inner: innerWidth, scroll: document.documentElement.scrollWidth})')
    case.check('no_document_overflow', metrics['scroll'] <= metrics['inner'] + 1, metrics)


def guard(page, case, mocks, body):
    errors = []
    page.on('pageerror', lambda exc: errors.append(f'pageerror: {exc}'))
    try:
        body()
    except Exception as exc:  # noqa: BLE001 -- a raised check is a failure
        case.check('raised', False, f'{type(exc).__name__}: {exc}'[:400])
        case.facts['trace'] = traceback.format_exc()[-1500:]
    finally:
        case.check('no_page_errors', not errors, errors[:5])
        case.check('no_unmocked_requests', not mocks.unexpected, mocks.unexpected[:5])
        page.close()


def run_initial_failure(context, surface, width):
    case = Case(f'initial-failure-{surface}-{width}')
    page = context.new_page()
    mocks = Mocks(page, chart='fail')

    def body():
        page.goto(f'{BASE}/radar/?span=1D&market=us#{surface}/AAPL', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-sp-state[role=alert]', timeout=20000)
        section = chart_section(page)
        text = section.inner_text()
        case.check('retry_state_shown', 'could not be loaded' in text and 'The chart data could not be read.' in text,
                   text[:300])
        case.check('retry_button_visible', section.get_by_role('button', name='Retry').is_visible())
        case.check('no_chart_drawn', page.locator('.rh-sp-svg').count() == 0 and page.locator('svg.pxchart').count() == 0)
        case.check('caption_not_loading', 'not loaded' in text, text[:160])
        no_overflow(page, case)
        case.facts['chart_requests'] = len(mocks.chart_requests)
        case.facts['shot'] = shoot(section, case.label)
    guard(page, case, mocks, body)


def run_refresh_failure_and_recovery(context, surface, width):
    case = Case(f'refresh-failure-{surface}-{width}')
    page = context.new_page()
    mocks = Mocks(page, chart_file='price-stale.json', chart='ok')

    def body():
        page.goto(f'{BASE}/radar/?span=1D&market=us#{surface}/AAPL', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-sp-svg', timeout=20000)
        section = chart_section(page)
        before = section.inner_text()
        labels = page.locator('.rh-sp-svg text').all_text_contents()
        case.check('answered_chart_had_live_wording', 'Current session so far' in before
                   and any(t.startswith('now') for t in labels), {'caption': before[:120], 'ends': labels[-3:]})
        case.facts['shot_answered'] = shoot(section, f'{case.label}-answered')
        # The fixture is a pending acquisition: the next poll comes in ~2 s.
        mocks.chart = 'fail'
        started = time.time()
        page.wait_for_selector('.rh-sp-state[role=alert]', timeout=20000)
        case.facts['seconds_until_retry_state'] = round(time.time() - started, 2)
        text = section.inner_text()
        case.check('retry_state_replaces_the_chart', page.locator('.rh-sp-svg').count() == 0
                   and 'earlier chart is hidden' in text, text[:300])
        case.check('no_old_now_or_current_session_wording',
                   not re.search(r'\bnow\b|Current session so far|so far', text), text[:300])
        case.check('caption_not_loaded', 'Current or last session · not loaded' in text, text[:160])
        case.check('legacy_chart_not_substituted', page.locator('svg.pxchart').count() == 0)
        no_overflow(page, case)
        case.facts['shot_failed'] = shoot(section, f'{case.label}-failed')
        mocks.chart = 'ok'
        section.get_by_role('button', name='Retry').click()
        page.wait_for_selector('.rh-sp-svg', timeout=20000)
        after = section.inner_text()
        case.check('recovered_chart_drawn', page.locator('.rh-sp-state[role=alert]').count() == 0
                   and 'Current session so far' in after, after[:160])
        no_overflow(page, case)
        case.facts['shot_recovered'] = shoot(section, f'{case.label}-recovered')
        case.facts['chart_requests'] = [r['mode'] for r in mocks.chart_requests]
    guard(page, case, mocks, body)


def run_admin(context, width, variant):
    case = Case(f'admin-{variant}-{width}')
    page = context.new_page()
    selected = (selected_ops(workers=None, started=None) if variant == 'unknown'
                else selected_ops(workers=2, started='2026-09-15T08:00:00Z'))
    mocks = Mocks(page, ops=ops_payload(selected))

    def body():
        page.goto(f'{BASE}/radar/#admin', wait_until='domcontentloaded')
        page.wait_for_selector('text=Selected price charts', timeout=20000)
        panel = page.locator('section.rh-panel').filter(has=page.get_by_role('heading', name='Selected price charts'))
        text = panel.inner_text()
        case.check('pid_and_scope_kept', 'This web process (pid 31337)' in text and 'reset when it restarts' in text,
                   text[:400])
        case.check('no_process_started_label', not re.search(r'process start', text, re.I))
        case.check('coordinator_label_present', 'Acquisition coordinator started' in text)
        if variant == 'unknown':
            case.check('workers_unknown_with_source',
                       'Unknown — WEB_CONCURRENCY is not set to a positive number; each worker keeps its own limits'
                       in text, text[:600])
            case.check('coordinator_not_started', 'not started in this process' in text)
        else:
            case.check('workers_from_source', '2 (from WEB_CONCURRENCY)' in text, text[:600])
            case.check('coordinator_start_stamp', '15 Sep, 10:00 Berlin' in text, text[:600])
        no_overflow(page, case)
        case.facts['shot'] = shoot(panel, case.label)
    guard(page, case, mocks, body)


def main():
    if not port_is_free():
        print(f'refusing: something already answers on 127.0.0.1:{PORT}')
        return 2
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    started = time.time()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            for width, height in ((1440, 1000), (390, 844)):
                context = browser.new_context(viewport={'width': width, 'height': height},
                                              has_touch=width < 768, is_mobile=width < 768,
                                              device_scale_factor=1)
                for surface in ('research', 'chatter'):
                    run_initial_failure(context, surface, width)
                    run_refresh_failure_and_recovery(context, surface, width)
                for variant in ('unknown', 'configured'):
                    run_admin(context, width, variant)
                context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    RESULTS['seconds'] = round(time.time() - started, 1)
    RESULTS['port_free_after'] = port_is_free()
    (HERE / 'results.json').write_text(json.dumps(RESULTS, indent=2), encoding='utf-8')
    summary = {label: (all(case['checks'].values()), len(case['checks'])) for label, case in RESULTS['cases'].items()}
    print(json.dumps({'failures': RESULTS['failures'], 'server_404': SERVER_LOG, 'cases': summary,
                      'checks': sum(n for _, n in summary.values()), 'seconds': RESULTS['seconds'],
                      'port_free_after': RESULTS['port_free_after']}, indent=1))
    return 1 if RESULTS['failures'] or SERVER_LOG else 0


if __name__ == '__main__':
    sys.exit(main())
