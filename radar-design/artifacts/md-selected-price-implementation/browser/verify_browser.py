"""MD-SELECTED-PRICE-IMPLEMENT-1: built-hub browser QA with python-playwright.

    py -3.12 -u radar-design/artifacts/md-selected-price-implementation/browser/verify_browser.py

FIXTURE evidence, not database, provider or production QA:
- Serves ONLY candidate files from a thread inside this process on
  127.0.0.1:5042 (refuses if anything answers there first): the real
  personal_apps/templates/radar/hub.html rendered with a synthetic shell
  (`?qa_flag=off` renders the flag off), and the built static/radar/dist bundle.
- Every /radar/api/* request is answered at the browser's network boundary by
  page.route from fixtures/ (see fixtures.py). Anything else reaching the
  server, or any unmocked API path, is a failure.
- Viewports 1440, 768, 390 and 320 (touch below 768), and REAL 200% browser
  zoom (headed Chromium with its own default page-zoom preference, windows 640
  and 780 device px = 320 and 390 CSS px), both chart surfaces: standalone
  Research and the Human Chatter research panel.

Writes results.json and screenshots/ next to this file; exits 1 on any failed
check. Screenshots must then be VIEWED.
"""
import base64
import json
import math
import mimetypes
import re
import socket
import sys
import tempfile
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
FIX = HERE / 'fixtures'
SHOTS = HERE / 'screenshots'
PORT = 5042
BASE = f'http://127.0.0.1:{PORT}'
MANIFEST = json.loads((FIX / 'manifest.json').read_text(encoding='utf-8'))
DIST_MANIFEST = json.loads((STATIC / 'radar' / 'dist' / '.vite' / 'manifest.json').read_text(encoding='utf-8'))
HUB_ENTRY = DIST_MANIFEST['static/radar/src/entries/hub.tsx']
ZOOM_LEVEL = math.log(2) / math.log(1.2)
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


# --- the loopback server: candidate files only ------------------------------------

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
            flag = parse_qs(parts.query).get('qa_flag', ['on'])[0] != 'off'
            html = ENV.get_template('radar/hub.html').render(
                shell={'board': board(), 'is_admin': False, 'selected_price_charts_enabled': flag})
            return self._send(200, html.encode('utf-8'), 'text/html; charset=utf-8')
        if parts.path.startswith('/static/'):
            target = (STATIC / unquote(parts.path[len('/static/'):])).resolve()
            if STATIC in target.parents and target.is_file():
                kind = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
                return self._send(200, target.read_bytes(), kind)
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


# --- the network boundary ------------------------------------------------------------

class Mocks:
    """What /radar/api/* answers for one page, by state."""

    def __init__(self, page, state, hold=()):
        self.state = state
        self.hold = set(hold)
        self.held = []
        self.chart_requests = []
        self.unexpected = []
        page.route('**/radar/api/**', self.handle)

    def chart_file(self, ticker, span):
        current = MANIFEST['states'].get(self.state)
        if current and current['ticker'] == ticker and current['span'] == span:
            return current['file']
        for info in MANIFEST['states'].values():
            if info['ticker'] == ticker and info['span'] == span and info.get('file'):
                return info['file']
        return None

    def handle(self, route):
        url = urlsplit(route.request.url)
        query = parse_qs(url.query, keep_blank_values=True)
        path = url.path
        if path == '/radar/api/board':
            return route.fulfill(json=board(query.get('sort', [None])[0], query.get('dir', ['desc'])[0]))
        if path == '/radar/api/search':
            return route.fulfill(json={'matches': []})
        chart = re.fullmatch(r'/radar/api/ticker/([^/]+)/price-chart', path)
        if chart:
            ticker = unquote(chart.group(1))
            span = query.get('span', [''])[0]
            self.chart_requests.append({'ticker': ticker, 'keys': sorted(query), 'query': query})
            if ticker == 'TSLA':
                return route.fulfill(status=422, json={'code': 'unsupported_instrument',
                                                        'error': 'no single eligible native-USD US primary'})
            name = self.chart_file(ticker, span)
            if name is None:
                self.unexpected.append(f'no chart fixture for {ticker} {span}')
                return route.fulfill(status=404, json={'code': 'unknown_ticker', 'error': 'no fixture'})
            body = load(name)
            if ticker in self.hold:
                self.held.append((route, body))
                return None
            return route.fulfill(json=body)
        detail = re.fullmatch(r'/radar/api/ticker/([^/]+)', path)
        if detail:
            ticker = unquote(detail.group(1))
            span = query.get('span', ['1D'])[0]
            file = FIX / f'detail-{ticker}-{span}.json'
            if file.exists():
                return route.fulfill(json=load(file.name))
        self.unexpected.append(route.request.url)
        return route.fulfill(status=404, json={'error': 'unmocked'})

    def release(self):
        outcomes = []
        for route, body in self.held:
            try:
                route.fulfill(json=body)
                outcomes.append('fulfilled after the reader had moved on')
            except Exception as exc:  # noqa: BLE001 -- a cancelled request is an outcome
                outcomes.append(f'not delivered: {type(exc).__name__}')
        self.held.clear()
        return outcomes


# --- checks ----------------------------------------------------------------------------

RESULTS = {'fixture_evidence': True, 'port': PORT, 'dist_hub': HUB_ENTRY['file'], 'cases': {},
           'failures': [], 'server_404': SERVER_LOG}


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


def section(page):
    return page.locator('section.rh-panel').filter(has=page.locator('.rh-spans')).first


def shoot(page, name, zoom, anchor='top'):
    """A viewport capture with the chart section placed under the sticky hub
    header. Element captures taller than the viewport stitch that header over
    the middle of the image, so they are only used where the section fits."""
    SHOTS.mkdir(exist_ok=True)
    path = SHOTS / f'{name}.png'
    target = section(page)
    fits = page.evaluate(
        "(el) => el.getBoundingClientRect().height <= innerHeight - 130", target.element_handle())
    page.evaluate("""([el, anchor]) => {
        const header = [...document.querySelectorAll('.rh-top, .rh-nav')]
          .reduce((h, n) => Math.max(h, n.getBoundingClientRect().bottom), 0)
        const box = anchor === 'readout' ? (el.querySelector('.rh-sp-readout') || el) : el
        const top = box.getBoundingClientRect().top + scrollY - header - 8
        const wanted = anchor === 'readout' ? top - innerHeight / 2 : top
        scrollTo({top: Math.max(0, wanted), behavior: 'instant'})
    }""", [target.element_handle(), anchor])
    page.wait_for_timeout(400)
    if zoom:
        cdp = page.context.new_cdp_session(page)
        path.write_bytes(base64.b64decode(cdp.send('Page.captureScreenshot', {'format': 'png'})['data']))
        cdp.detach()
    elif fits and anchor == 'top':
        target.screenshot(path=str(path))
    else:
        page.screenshot(path=str(path))
    return path.name


def tab_to(page, selector, limit=400):
    page.evaluate('document.activeElement && document.activeElement.blur()')
    for count in range(1, limit + 1):
        page.keyboard.press('Tab')
        if page.evaluate(f'!!document.activeElement && document.activeElement.matches({json.dumps(selector)})'):
            return count
    return None


def run_case(context, label, state, surface, *, zoom=False, narrow=False, flag=True):
    info = MANIFEST['states'][state]
    ticker, span = info['ticker'], info['span']
    case = Case(label)
    case.facts.update(state=state, surface=surface, ticker=ticker, span=span, zoom=zoom,
                      description=info['description'])
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda exc: errors.append(f'pageerror: {exc}'))
    page.on('console', lambda msg: errors.append(f'console.{msg.type}: {msg.text}')
            if msg.type == 'error' else None)
    mocks = Mocks(page, state)
    try:
        query = f'span={span}&market=us' + ('' if flag else '&qa_flag=off')
        page.goto(f'{BASE}/radar/?{query}#{surface}/{ticker}', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-sp-svg, .rh-sp-state[role=alert], svg.pxchart', timeout=20000)
        page.wait_for_timeout(400)
        metrics = page.evaluate('({inner: innerWidth, outer: outerWidth, dpr: devicePixelRatio,'
                                ' scroll: document.documentElement.scrollWidth})')
        case.facts['metrics'] = metrics
        if zoom:
            case.check('real_zoom_in_effect', metrics['dpr'] >= 1.9 and metrics['outer'] >= 1.8 * metrics['inner'],
                       metrics)
        case.check('no_document_overflow', metrics['scroll'] <= metrics['inner'] + 1, metrics)
        case.facts['headline'] = {
            'price': page.locator('.rh-bigprice').first.inner_text(),
            'provenance': page.locator('[data-testid=rh-quote-provenance]').first.inner_text()}
        if not flag:
            case.check('flag_off_draws_the_original_chart', page.locator('svg.pxchart').count() == 1)
            case.check('flag_off_sends_no_chart_request', not mocks.chart_requests)
            case.facts['shot'] = shoot(page, label, zoom)
            return case
        if ticker == 'TSLA':
            page.wait_for_selector('svg.pxchart', timeout=10000)
            case.check('unsupported_instrument_keeps_the_original_chart',
                       page.locator('svg.pxchart').count() == 1 and page.locator('.rh-sp-svg').count() == 0)
            case.facts['shot'] = shoot(page, label, zoom)
            return case
        case.check('new_chart_rendered', page.locator('.rh-sp-svg').count() == 1)
        case.check('old_chart_not_rendered', page.locator('svg.pxchart').count() == 0)
        keys = [r['keys'] for r in mocks.chart_requests]
        case.check('chart_request_has_only_span_market_sources',
                   bool(keys) and all(k == ['market', 'sources', 'span'] for k in keys), keys)
        meta = page.locator('.rh-sp-meta').inner_text()
        case.check('session_dates_labelled', info['sessions_label'] in meta, meta)
        labels = page.locator('.rh-sp-svg text').all_text_contents()   # SVG text has no innerText
        end = [text for text in labels if 'now' in text or 'session end' in text]
        case.check('end_label_matches_window_state',
                   bool(end) and (any(t.startswith('now') for t in end) if info['partial']
                                  else all('session end' in t for t in end)), end)
        summary = page.locator('.rh-sp-summary').inner_text()
        case.check('summary_names_this_company', summary.startswith(f'{ticker},'), summary[:120])
        case.check('no_return_or_direction_claim', not re.search(r'over this span|\d%', meta + summary))
        wrap = page.evaluate("(() => { const b = document.querySelector('.rh-sp-wrap');"
                             " return {sw: b.scrollWidth, cw: b.clientWidth, left: b.scrollLeft}; })()")
        case.facts['pan'] = wrap
        if wrap['sw'] > wrap['cw'] + 1:
            case.check('narrow_chart_pans_opened_at_newest_end', wrap['left'] > 0, wrap)
        tabs = tab_to(page, '.rh-sp-canvas')
        case.check('chart_reachable_by_keyboard', tabs is not None, tabs)
        if tabs is not None:
            page.keyboard.press('End')
            last = page.locator('[data-testid=rh-sp-readout]').inner_text()
            page.keyboard.press('ArrowLeft')
            previous = page.locator('[data-testid=rh-sp-readout]').inner_text()
            page.keyboard.press('Home')
            first = page.locator('[data-testid=rh-sp-readout]').inner_text()
            case.facts['readouts'] = {'end': last, 'left': previous, 'home': first}
            case.check('keyboard_readout_reports_interval_count_and_price',
                       all(('mention' in text) and ('price' in text) for text in (last, previous, first))
                       and last != previous, case.facts['readouts'])
            focus = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
            case.check('focus_is_visible', focus not in ('none', ''), focus)
        case.facts['shot'] = shoot(page, label, zoom)
        if tabs is not None:
            page.keyboard.press('End')
            case.facts['shot_focus'] = shoot(page, f'{label}-focus', zoom, anchor='readout')
    except Exception as exc:  # noqa: BLE001 -- a raised check is a failure
        case.check('raised', False, f'{type(exc).__name__}: {exc}'[:400])
        case.facts['trace'] = traceback.format_exc()[-1500:]
    finally:
        case.check('no_page_errors', not [e for e in errors if e.startswith('pageerror')], errors[:5])
        case.facts['console_errors'] = errors[:10]
        case.check('no_unmocked_requests', not mocks.unexpected, mocks.unexpected[:5])
        page.close()
    return case


def run_switch(context, label):
    """A late answer for the company the reader left never draws under the next."""
    case = Case(label)
    case.facts.update(state='stale-switch', surface='research')
    page = context.new_page()
    mocks = Mocks(page, 'partial_gap', hold={'AAPL'})
    try:
        page.goto(f'{BASE}/radar/?span=1D&market=us#research/AAPL', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-sp-state[role=status]', timeout=20000)
        case.check('old_company_is_loading', 'AAPL' in page.locator('.rh-sp-state').inner_text())
        mocks.state = 'fallback'
        page.evaluate("location.hash = '#research/MSFT'")
        page.wait_for_function("(() => { const s = document.querySelector('.rh-sp-summary');"
                               " return s && s.textContent.startsWith('MSFT,'); })()", timeout=20000)
        case.facts['late_delivery'] = mocks.release()
        page.wait_for_timeout(1500)
        summary = page.locator('.rh-sp-summary').inner_text()
        case.check('late_old_answer_not_drawn', summary.startswith('MSFT,') and 'AAPL' not in summary,
                   summary[:100])
        case.check('heading_is_the_new_company', 'Microsoft' in page.locator('h1').first.inner_text())
        case.facts['shot'] = shoot(page, label, False)
    except Exception as exc:  # noqa: BLE001
        case.check('raised', False, f'{type(exc).__name__}: {exc}'[:400])
    finally:
        page.close()


SURFACES = ('research', 'chatter')


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
            for width, height in ((1440, 1000), (768, 1024), (390, 844), (320, 844)):
                context = browser.new_context(viewport={'width': width, 'height': height},
                                              has_touch=width < 768, is_mobile=width < 768,
                                              device_scale_factor=1)
                states = list(MANIFEST['states']) if width in (1440, 390) else [
                    'ordinary', 'partial_gap', 'fallback', 'unavailable', 'long']
                for state in states:
                    for surface in SURFACES:
                        run_case(context, f'{state}-{surface}-{width}', state, surface)
                if width in (1440, 390):
                    run_switch(context, f'stale-switch-{width}')
                    unsupported = dict(MANIFEST['states']['ordinary'], ticker='TSLA', span='1W')
                    MANIFEST['states']['unsupported'] = dict(unsupported, file=None, partial=True,
                                                             description='422 unsupported instrument')
                    run_case(context, f'unsupported-research-{width}', 'unsupported', 'research')
                    del MANIFEST['states']['unsupported']
                context.close()
            # Headline unchanged: the same company with the flag off.
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            on = RESULTS['cases']['ordinary-research-1440'].get('headline')
            off_case = run_case(context, 'flag-off-research-1440', 'ordinary', 'research', flag=False)
            off_case.check('headline_unchanged_by_the_flag', on is not None and on == off_case.facts.get('headline'),
                           {'on': on, 'off': off_case.facts.get('headline')})
            context.close()
            browser.close()

            for css, window_width in ((320, 640), (390, 780)):
                with tempfile.TemporaryDirectory(prefix='md-sp-zoom-') as profile:
                    default = Path(profile) / 'Default'
                    default.mkdir()
                    (default / 'Preferences').write_text(json.dumps(
                        {'partition': {'default_zoom_level': {'x': ZOOM_LEVEL}}}), encoding='utf-8')
                    context = playwright.chromium.launch_persistent_context(
                        profile, headless=False, no_viewport=True,
                        args=[f'--window-size={window_width},900', '--window-position=-2400,0'])
                    try:
                        for state in ('ordinary', 'partial_gap'):
                            for surface in SURFACES:
                                run_case(context, f'zoom200-{state}-{surface}-{css}css', state, surface, zoom=True)
                    finally:
                        for page in context.pages:
                            page.close()
                        context.close()
    finally:
        server.shutdown()
        server.server_close()
    RESULTS['seconds'] = round(time.time() - started, 1)
    RESULTS['port_free_after'] = port_is_free()
    (HERE / 'results.json').write_text(json.dumps(RESULTS, indent=2), encoding='utf-8')
    summary = {label: (all(case['checks'].values()), len(case['checks'])) for label, case in RESULTS['cases'].items()}
    print(json.dumps({'failures': RESULTS['failures'], 'server_404': SERVER_LOG, 'cases': summary,
                      'seconds': RESULTS['seconds'], 'port_free_after': RESULTS['port_free_after']}, indent=1))
    return 1 if RESULTS['failures'] or SERVER_LOG else 0


if __name__ == '__main__':
    sys.exit(main())
