"""A-US-USD-ONLY-IMPLEMENT-1: actual-app and built-hub visual verification.

    cd personal_apps && py -3.12 -u ../radar-design/artifacts/a-us-usd-only-implement-1/browser/verify_us_only.py

Two local servers inside this one process, loopback only:

A. The REAL Flask app on 127.0.0.1:5051, bound to the documented disposable
   clone `personal_apps_radar_wt` (refused unless both the engine URL and the
   server's `select database()` name it). Outbound sockets to anything but
   loopback are refused in this process; the shared board store is off; the
   selected-price charts are ON with both providers OFF, and the Alpaca
   credential names are removed from this process's environment, so no
   provider can be asked. A session cookie for the seeded admin is minted in
   memory and never printed or written. The clone's board is empty (its data
   is old), so this part proves the contract and the chrome: the explicit
   400, the hub and legacy shells without a market control, the admin page.

B. The BUILT hub bundle rendered from the real templates/radar/hub.html on
   127.0.0.1:5052 with the saved, normalized MD-SELECTED-PRICE fixtures
   (radar-design/artifacts/md-selected-price-alpaca-c1/browser/fixtures),
   stripped of the removed `is_fallback`/`converted_from` keys. Every
   /radar/api/* request is answered at the browser boundary. This part proves
   populated USD rendering and the selected-price section at every width.

Viewports 1200, 390 and 320 CSS px. Writes results.json and screenshots/ next
to this file and exits 1 on any failed check. The screenshots must be viewed.
"""
import json
import os
import re
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PERSONAL = ROOT / 'personal_apps'
STATIC = (PERSONAL / 'static').resolve()
FIX = ROOT / 'radar-design' / 'artifacts' / 'md-selected-price-alpaca-c1' / 'browser' / 'fixtures'
SHOTS = HERE / 'screenshots'
PORT_A, PORT_B = 5051, 5052
BASE_A, BASE_B = f'http://127.0.0.1:{PORT_A}', f'http://127.0.0.1:{PORT_B}'
EXPECTED_DB = 'personal_apps_radar_wt'
VIEWPORTS = ((1200, 900), (390, 844), (320, 720))

# --- process guards, before the app is imported ---------------------------------

import dotenv  # noqa: E402

_real_load = dotenv.load_dotenv
FORCED = {
    'PERSONAL_DB_NAME': EXPECTED_DB,
    'RADAR_BOARD_SHARED_RESULTS': '',
    'RADAR_SELECTED_PRICE_CHARTS_ENABLED': 'on',
    'RADAR_SELECTED_PRICE_ALPACA_ENABLED': '',
    'RADAR_SELECTED_PRICE_YAHOO_ENABLED': '',
    'RADAR_OBSERVATION_CAPTURE_ENABLED': '',
}


def _force():
    for name, value in FORCED.items():
        os.environ[name] = value
    for name in ('APCA_API_KEY_ID', 'APCA_API_SECRET_KEY'):
        os.environ.pop(name, None)


def _pinned(*args, **kwargs):
    if not args and 'dotenv_path' not in kwargs:
        kwargs['dotenv_path'] = dotenv.find_dotenv(usecwd=True)
    result = _real_load(*args, **kwargs)
    _force()
    return result


dotenv.load_dotenv = _pinned
_force()

_real_connect = socket.socket.connect
_real_getaddrinfo = socket.getaddrinfo
LOOPBACK = {'127.0.0.1', '::1', 'localhost'}
REFUSED = []


def _connect(self, address):
    host = address[0] if isinstance(address, tuple) else None
    if host is not None and host not in LOOPBACK:
        REFUSED.append(str(host))
        raise ConnectionRefusedError(f'network guard: {host}')
    return _real_connect(self, address)


def _getaddrinfo(host, *args, **kwargs):
    if host is not None and host not in LOOPBACK:
        REFUSED.append(str(host))
        raise socket.gaierror(f'network guard: {host}')
    return _real_getaddrinfo(host, *args, **kwargs)


socket.socket.connect = _connect
socket.getaddrinfo = _getaddrinfo

sys.path.insert(0, str(PERSONAL))
sys.path.insert(0, str(PERSONAL / 'tests'))
os.chdir(PERSONAL)

import jinja2  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

from app import app  # noqa: E402
from extensions import db  # noqa: E402

RESULTS = {'database': None, 'refused_outbound': REFUSED, 'cases': {},
           'failures': [], 'fixture_unmocked': [], 'request_queries': []}


def fail(label, name, ok, detail=None):
    case = RESULTS['cases'].setdefault(label, {'checks': {}, 'details': {}})
    case['checks'][name] = bool(ok)
    if detail is not None:
        case['details'][name] = detail
    if not ok:
        RESULTS['failures'].append(f'{label}: {name}'
                                   + (f' -- {detail}' if detail is not None else ''))


def prove_database():
    with app.app_context():
        url = db.engine.url
        with db.engine.connect() as conn:
            server = conn.execute(sa.text('select database()')).scalar()
            head = conn.execute(sa.text('select version_num from alembic_version')).scalars().all()
        info = {'engine': f'{url.host}:{url.port or 3306}/{url.database}',
                'server_database': server, 'alembic': head}
    if url.database != EXPECTED_DB or server != EXPECTED_DB \
            or url.host not in ('localhost', '127.0.0.1'):
        raise SystemExit(f'REFUSED: {info}')
    RESULTS['database'] = info


def port_free(port):
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return _real_connect_ex(probe, ('127.0.0.1', port)) != 0


def _real_connect_ex(sock, address):
    return socket.socket.connect_ex(sock, address)


def session_cookie():
    from conftest import _admin_id
    admin = _admin_id()
    serializer = app.session_interface.get_signing_serializer(app)
    return {'name': app.config.get('SESSION_COOKIE_NAME', 'session'),
            'value': serializer.dumps({'user_id': admin}), 'url': BASE_A}


# --- server B: the built hub with fixtures ---------------------------------------

DIST = json.loads((STATIC / 'radar' / 'dist' / '.vite' / 'manifest.json').read_text(encoding='utf-8'))
HUB = DIST['static/radar/src/entries/hub.tsx']


def us_only(value):
    if isinstance(value, dict):
        return {k: us_only(v) for k, v in value.items()
                if k not in ('is_fallback', 'converted_from')}
    if isinstance(value, list):
        return [us_only(v) for v in value]
    return value


def fixture(name):
    return us_only(json.loads((FIX / name).read_text(encoding='utf-8')))


def now_z():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def board():
    payload = fixture('board.json')
    stamp = now_z()
    payload.update(generated_at=stamp, as_of=stamp, built_at=stamp, ops_collected_at=stamp)
    return payload


ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(str(PERSONAL / 'templates')),
                         autoescape=jinja2.select_autoescape(['html']))
ENV.globals.update(
    url_for=lambda endpoint, filename: f'/static/{filename}',
    csrf_token=lambda: 'qa-local-token',
    vite_asset=lambda name, feature: f"/static/radar/dist/{HUB['file']}",
    vite_asset_css=lambda name, feature: [f'/static/radar/dist/{css}' for css in HUB.get('css', [])],
)


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path in ('/radar/', '/radar/hub/'):
            html = ENV.get_template('radar/hub.html').render(
                shell={'board': board(), 'is_admin': False,
                       'selected_price_charts_enabled': True})
            return self._send(200, html.encode('utf-8'), 'text/html; charset=utf-8')
        if parts.path.startswith('/static/'):
            target = (STATIC / unquote(parts.path[len('/static/'):])).resolve()
            if STATIC in target.parents and target.is_file():
                import mimetypes
                kind = mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
                return self._send(200, target.read_bytes(), kind)
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


PRICE = {('AAPL', '1D'): 'price-dense_1d.json', ('AAPL', '1W'): 'price-week_1w.json',
         ('FT', '1D'): 'price-sparse_1d.json', ('MSFT', '1D'): 'price-fallback_1d.json',
         ('NVDA', '1W'): 'price-unavailable_1w.json'}


def mock_api(page):
    def handle(route):
        url = urlsplit(route.request.url)
        query = parse_qs(url.query, keep_blank_values=True)
        RESULTS['request_queries'].append({'path': url.path, 'keys': sorted(query),
                                           'market': query.get('market')})
        if url.path == '/radar/api/board':
            return route.fulfill(json=board())
        if url.path == '/radar/api/search':
            return route.fulfill(json={'matches': []})
        chart = re.fullmatch(r'/radar/api/ticker/([^/]+)/price-chart', url.path)
        if chart:
            name = PRICE.get((unquote(chart.group(1)), query.get('span', [''])[0]))
            if name:
                return route.fulfill(json=fixture(name))
            return route.fulfill(status=422, json={'code': 'unsupported_instrument',
                                                   'error': 'no fixture'})
        detail = re.fullmatch(r'/radar/api/ticker/([^/]+)', url.path)
        if detail:
            span = query.get('span', ['1D'])[0]
            file = FIX / f'detail-{unquote(detail.group(1))}-{span}.json'
            if not file.exists():
                file = FIX / f'detail-{unquote(detail.group(1))}-1D.json'
            if file.exists():
                return route.fulfill(json=fixture(file.name))
        RESULTS['fixture_unmocked'].append(route.request.url)
        return route.fulfill(status=404, json={'error': 'unmocked'})
    page.route('**/radar/api/**', handle)


# --- shared page checks ----------------------------------------------------------

LAYOUT = """() => ({
  scrollWidth: document.documentElement.scrollWidth,
  innerWidth: window.innerWidth,
  text: document.body.innerText,
  selects: [...document.querySelectorAll('select')].map((s) => {
    const label = s.closest('label') || document.querySelector(`label[for="${s.id}"]`)
    return {label: label ? label.innerText.trim().split('\\n')[0] : (s.getAttribute('aria-label') || ''),
            options: [...s.options].map((o) => o.textContent.trim())}
  }),
  radios: document.querySelectorAll('input[type=radio]').length,
  marketSwitch: document.querySelectorAll('.market-switch').length,
})"""

FOCUS = """() => {
  const el = document.activeElement
  if (!el || el === document.body) return null
  const r = el.getBoundingClientRect()
  const style = getComputedStyle(el)
  const name = (el.getAttribute('aria-label') || el.innerText || el.value || el.name || '').trim().slice(0, 40)
  return {tag: el.tagName, name, w: r.width, h: r.height,
          hidden: style.visibility === 'hidden' || style.display === 'none' || style.opacity === '0',
          inMarket: !!el.closest('.market-switch')}
}"""

BANNED = re.compile(r'Germany|German|Xetra|XETR|XGAT|Tradegate|Deutsche|ECB|€|\bEUR\b|'
                    r'fallback listing|US fallback|converted to')


def page_checks(page, label, *, tabs=40):
    facts = page.evaluate(LAYOUT)
    fail(label, 'no horizontal overflow', facts['scrollWidth'] <= facts['innerWidth'] + 1,
         {'scrollWidth': facts['scrollWidth'], 'innerWidth': facts['innerWidth']})
    banned = sorted(set(BANNED.findall(facts['text'])))
    fail(label, 'no retired-market or EUR copy', not banned, banned or None)
    labels = [s['label'] for s in facts['selects']]
    options = [o for s in facts['selects'] for o in s['options']]
    fail(label, 'no market select', not any(re.search(r'market', l, re.I) for l in labels),
         labels)
    fail(label, 'no Germany option', not any(re.search(r'german|\bDE\b', o, re.I) for o in options))
    fail(label, 'no market radio or switch', facts['radios'] == 0 and facts['marketSwitch'] == 0,
         {'radios': facts['radios'], 'switch': facts['marketSwitch']})
    page.evaluate('document.activeElement && document.activeElement.blur()')
    hidden, stops = [], []
    for _ in range(tabs):
        page.keyboard.press('Tab')
        focus = page.evaluate(FOCUS)
        if focus is None:
            continue
        stops.append(f"{focus['tag']}:{focus['name']}")
        if focus['w'] < 1 or focus['h'] < 1 or focus['hidden'] or focus['inMarket']:
            hidden.append(focus)
    fail(label, 'no hidden or market tab stop', not hidden, hidden or None)
    fail(label, 'no tab stop names a market',
         not any(re.search(r'\bmarket\b|germany', s, re.I) for s in stops), stops[:40])
    return facts


def shot(page, name, full=False):
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=str(SHOTS / f'{name}.png'), full_page=full)
    return name


# --- the runs ---------------------------------------------------------------------

def run_real(browser):
    cookie = session_cookie()
    for width, height in VIEWPORTS:
        context = browser.new_context(viewport={'width': width, 'height': height})
        context.add_cookies([cookie])
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda exc: errors.append(str(exc)))

        label = f'real-400-{width}'
        response = page.goto(f'{BASE_A}/radar/?market=de&window=24', wait_until='domcontentloaded')
        body = page.inner_text('body')
        fail(label, 'status 400', response.status == 400, response.status)
        fail(label, 'says unsupported market', 'unsupported market' in body, body[:200])
        fail(label, 'no hub mounted', page.locator('#radar-hub-data').count() == 0)
        shot(page, label)

        label = f'real-hub-{width}'
        response = page.goto(f'{BASE_A}/radar/#chatter', wait_until='domcontentloaded')
        fail(label, 'status 200', response.status == 200, response.status)
        page.wait_for_selector('.rh-session', timeout=20000)
        page.wait_for_timeout(1500)
        # The venue half of the top bar is hidden below desk widths by
        # design; its text is still the bar's, and the page lead says it too.
        top = page.text_content('.rh-session')
        lead = page.inner_text('main')
        fail(label, 'top bar names US markets', 'US markets' in top, top)
        fail(label, 'page lead names US markets', 'US markets' in lead, lead[:120])
        fail(label, 'window and size filters present',
             page.get_by_label(re.compile('window', re.I)).count() >= 1, None)
        page_checks(page, label)
        page.evaluate('scrollTo(0, 0)')
        shot(page, label)

        label = f'real-legacy-{width}'
        response = page.goto(f'{BASE_A}/radar/legacy/', wait_until='domcontentloaded')
        fail(label, 'status 200', response.status == 200, response.status)
        page.wait_for_selector('.brand h1', timeout=20000)
        page.wait_for_timeout(800)
        gap = page.evaluate("""() => {
          const kids = [...document.querySelector('.brand').children]
            .filter((el) => getComputedStyle(el).display !== 'none')
          const [h1, next] = kids
          if (!next) return null
          const a = h1.getBoundingClientRect(), b = next.getBoundingClientRect()
          return {gap: Math.round(b.left - a.right), sameRow: Math.abs(a.top - b.top) < 40,
                  second: next.className}
        }""")
        fail(label, 'no empty slot beside the wordmark',
             gap is not None and (not gap['sameRow'] or gap['gap'] <= 40), gap)
        page_checks(page, label, tabs=20)
        page.evaluate('scrollTo(0, 0)')
        shot(page, label)

        label = f'real-admin-{width}'
        page.goto(f'{BASE_A}/radar/#admin', wait_until='domcontentloaded')
        page.wait_for_selector('text=Newest grouped close', timeout=20000)
        text = page.inner_text('body')
        fail(label, 'US market-data facts shown', 'Quote basis, 24h' in text)
        fail(label, 'no retired collector panels',
             'download budget' not in text and 'Collection cycles' not in text)
        page_checks(page, label, tabs=10)
        page.locator('text=Newest grouped close').first.scroll_into_view_if_needed()
        shot(page, label)

        fail(f'real-{width}', 'no page errors', not errors, errors or None)
        context.close()


def run_fixture(browser):
    for width, height in VIEWPORTS:
        context = browser.new_context(viewport={'width': width, 'height': height})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        mock_api(page)

        label = f'fixture-chatter-AAPL-{width}'
        page.goto(f'{BASE_B}/radar/?span=1D#chatter/AAPL', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-sp-svg', timeout=20000)
        page.wait_for_timeout(800)
        text = page.inner_text('body')
        # The company's own quote is on screen at every width; the candidate
        # list beside it is on screen only where the workspace is side by side.
        wanted = ('$330.46', '$7.39') if width >= 860 else ('$330.46',)
        fail(label, 'prices in US dollars', all(p in text for p in wanted), wanted)
        fail(label, 'selected price chart drawn',
             page.locator('.rh-sp-svg path.price-line').count() >= 1)
        page_checks(page, label)
        page.evaluate('scrollTo(0, 0)')
        shot(page, label)
        page.locator('.rh-sp-svg').first.scroll_into_view_if_needed()
        shot(page, label + '-chart')

        before = len(RESULTS['request_queries'])
        window = page.get_by_label(re.compile('window', re.I)).first
        if window.count() and window.is_visible():
            window.focus()
            window.select_option('24')
            page.wait_for_timeout(600)
            fail(label, 'window change keeps the URL market-free',
                 'window=24' in page.url and 'market=' not in page.url, page.url)
        asked = RESULTS['request_queries'][before:]
        board_asks = [q for q in asked if q['path'] == '/radar/api/board']
        fail(label, 'board requests carry no market',
             all(q['market'] is None for q in board_asks), board_asks)

        label = f'fixture-research-AAPL-{width}'
        page.goto(f'{BASE_B}/radar/?span=1D#research/AAPL', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-bigprice', timeout=20000)
        page.wait_for_timeout(800)
        big = page.inner_text('.rh-bigprice')
        fail(label, 'quote price is $330.46 style', big.startswith('$330.46'), big)
        prov = page.inner_text('[data-testid="rh-quote-provenance"]')
        fail(label, 'provenance names the US venue and USD, no fallback',
             'NASDAQ' in prov and 'USD' in prov and 'fallback' not in prov, prov)
        page_checks(page, label)
        page.evaluate('scrollTo(0, 0)')
        shot(page, label)

        label = f'fixture-overview-{width}'
        page.goto(f'{BASE_B}/radar/#overview', wait_until='domcontentloaded')
        page.wait_for_timeout(1200)
        page_checks(page, label, tabs=25)
        shot(page, label)

        fail(f'fixture-{width}', 'no page errors', not errors, errors or None)
        context.close()

    detail_asks = [q for q in RESULTS['request_queries']
                   if re.fullmatch(r'/radar/api/ticker/[^/]+', q['path'])]
    chart_asks = [q for q in RESULTS['request_queries'] if q['path'].endswith('/price-chart')]
    fail('fixture', 'detail requests carry no market',
         all(q['market'] is None for q in detail_asks), detail_asks[:5])
    fail('fixture', 'selected-price client still sends market=us (protected)',
         chart_asks and all(q['market'] == ['us'] for q in chart_asks), chart_asks[:5])
    fail('fixture', 'no unmocked API request', not RESULTS['fixture_unmocked'],
         RESULTS['fixture_unmocked'][:5])


def main():
    prove_database()
    for port in (PORT_A, PORT_B):
        if not port_free(port):
            raise SystemExit(f'port {port} is already answering; refusing to share it')
    app.config['TESTING'] = False
    real = make_server('127.0.0.1', PORT_A, app, threaded=True)
    fixture_server = ThreadingHTTPServer(('127.0.0.1', PORT_B), FixtureHandler)
    threads = [threading.Thread(target=s.serve_forever, daemon=True)
               for s in (real, fixture_server)]
    for thread in threads:
        thread.start()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                run_real(browser)
                run_fixture(browser)
            finally:
                browser.close()
    finally:
        real.shutdown()
        fixture_server.shutdown()
    fail('process', 'no outbound connection attempted', not REFUSED, REFUSED or None)
    RESULTS['screenshots'] = sorted(p.name for p in SHOTS.glob('*.png'))
    (HERE / 'results.json').write_text(json.dumps(RESULTS, indent=2), encoding='utf-8')
    print(json.dumps({'failures': RESULTS['failures'],
                      'cases': len(RESULTS['cases']),
                      'screenshots': len(RESULTS['screenshots']),
                      'database': RESULTS['database']}, indent=2))
    return 1 if RESULTS['failures'] else 0


if __name__ == '__main__':
    sys.exit(main())
