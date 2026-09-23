"""MD-SELECTED-PRICE-ALPACA-C1: built-hub visual verification with python-playwright.

    py -3.12 -u radar-design/artifacts/md-selected-price-alpaca-c1/browser/verify_browser.py

FIXTURE evidence, not database, provider or production QA:
- Serves ONLY candidate files from a thread inside this process on
  127.0.0.1:5043 (refuses if anything answers there first): the real
  personal_apps/templates/radar/hub.html rendered with a synthetic shell, and
  the built static/radar/dist bundle.
- Every /radar/api/* request is answered at the browser's network boundary by
  page.route from fixtures/ (see fixtures.py). Anything else reaching the
  server, or any unmocked API path, is a failure.
- Viewports 1200, 768 and 390 CSS px, plus REAL 200% browser zoom (headed
  Chromium with its own default page-zoom preference, a 780 device-px window =
  390 CSS px), on both chart surfaces: standalone Research and the Human
  Chatter research panel.

No credential is read and no provider is contacted: the fixtures are already
normalized answers.

Writes results.json and screenshots/ next to this file; exits 1 on any failed
check. The screenshots must then be VIEWED and compared with the accepted
area preview.
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
PORT = 5043
BASE = f'http://127.0.0.1:{PORT}'
MANIFEST = json.loads((FIX / 'manifest.json').read_text(encoding='utf-8'))
DIST_MANIFEST = json.loads((STATIC / 'radar' / 'dist' / '.vite' / 'manifest.json').read_text(encoding='utf-8'))
HUB_ENTRY = DIST_MANIFEST['static/radar/src/entries/hub.tsx']
ZOOM_LEVEL = math.log(2) / math.log(1.2)
#: selectedPriceGeometry.PLOT_R, in the SVG's own user units.
PLOT_R = 848
SERVER_LOG = []


def load(name):
    return json.loads((FIX / name).read_text(encoding='utf-8'))


def now_z():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def board():
    payload = load('board.json')
    stamp = now_z()
    payload.update(generated_at=stamp, as_of=stamp, built_at=stamp, ops_collected_at=stamp)
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
            html = ENV.get_template('radar/hub.html').render(
                shell={'board': board(), 'is_admin': False, 'selected_price_charts_enabled': True})
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
    def __init__(self, page, state):
        self.state = state
        self.chart_requests = []
        self.unexpected = []
        page.route('**/radar/api/**', self.handle)

    def handle(self, route):
        url = urlsplit(route.request.url)
        query = parse_qs(url.query, keep_blank_values=True)
        path = url.path
        if path == '/radar/api/board':
            return route.fulfill(json=board())
        if path == '/radar/api/search':
            return route.fulfill(json={'matches': []})
        chart = re.fullmatch(r'/radar/api/ticker/([^/]+)/price-chart', path)
        if chart:
            info = MANIFEST['states'][self.state]
            ticker = unquote(chart.group(1))
            span = query.get('span', [''])[0]
            self.chart_requests.append({'ticker': ticker, 'keys': sorted(query)})
            if ticker != info['ticker'] or span != info['span']:
                self.unexpected.append(f'chart asked for {ticker} {span}, state is {info["ticker"]} {info["span"]}')
                return route.fulfill(status=404, json={'code': 'unknown_ticker', 'error': 'no fixture'})
            return route.fulfill(json=load(info['file']))
        detail = re.fullmatch(r'/radar/api/ticker/([^/]+)', path)
        if detail:
            ticker = unquote(detail.group(1))
            span = query.get('span', ['1D'])[0]
            file = FIX / f'detail-{ticker}-{span}.json'
            if file.exists():
                return route.fulfill(json=load(file.name))
        self.unexpected.append(route.request.url)
        return route.fulfill(status=404, json={'error': 'unmocked'})


# --- checks ----------------------------------------------------------------------------

RESULTS = {'fixture_evidence': True, 'live_provider_requests': 0, 'port': PORT,
           'dist_hub': HUB_ENTRY['file'], 'cases': {}, 'failures': [], 'server_404': SERVER_LOG}


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


def shoot(page, name, zoom, anchor='section'):
    """`anchor='section'` frames the whole chart section; `anchor='chart'`
    frames the drawing itself, which is the only way to SEE it where the
    section is taller than a phone viewport."""
    SHOTS.mkdir(exist_ok=True)
    path = SHOTS / f'{name}.png'
    target = section(page)
    fits = page.evaluate(
        "(el) => el.getBoundingClientRect().height <= innerHeight - 130", target.element_handle())
    page.evaluate("""([el, anchor]) => {
        const header = [...document.querySelectorAll('.rh-top, .rh-nav')]
          .reduce((h, n) => Math.max(h, n.getBoundingClientRect().bottom), 0)
        const box = anchor === 'chart' ? (el.querySelector('.rh-sp-wrap') || el) : el
        scrollTo({top: Math.max(0, box.getBoundingClientRect().top + scrollY - header - 8),
                  behavior: 'instant'})
    }""", [target.element_handle(), anchor])
    page.wait_for_timeout(400)
    if zoom:
        cdp = page.context.new_cdp_session(page)
        path.write_bytes(base64.b64decode(cdp.send('Page.captureScreenshot', {'format': 'png'})['data']))
        cdp.detach()
    elif fits and anchor == 'section':
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


GEOMETRY = """(() => {
  const svg = document.querySelector('.rh-sp-svg')
  if (!svg) return null
  const vertices = (d) => (d.match(/[ML]/g) || []).length
  const xs = (d) => [...d.matchAll(/[ML](-?[\\d.]+),/g)].map((m) => Number(m[1]))
  const lines = [...svg.querySelectorAll('path.price-line')].map((p) => p.getAttribute('d'))
  const areas = [...svg.querySelectorAll('path.rh-sp-area')].map((p) => ({
    d: p.getAttribute('d'), fill: p.getAttribute('fill') }))
  return {
    lines: lines.length,
    line_vertices: lines.map(vertices),
    areas: areas.length,
    area_vertices: areas.map((a) => vertices(a.d)),
    area_closed: areas.every((a) => a.d.trim().endsWith('Z')),
    area_fill_is_a_gradient: areas.every((a) => /^url\\(#/.test(a.fill || '')),
    area_spans: areas.map((a) => { const v = xs(a.d); return Math.max(...v) - Math.min(...v) }),
    dots: svg.querySelectorAll('circle.price-dot').length,
    latest: svg.querySelectorAll('circle.price-last, circle.price-provisional').length,
    gradients: svg.querySelectorAll('linearGradient').length,
  }
})()"""


#: What the panned scroller shows at rest: where it sits, whether the latest
#: observation is on screen, whether the price-axis gutter is on screen, and
#: whether BOTH could have fitted (the rightmost position still leaving half a
#: viewport of line to the left of the latest observation).
PAN = """(() => {
  const box = document.querySelector('.rh-sp-wrap')
  const outer = box.getBoundingClientRect()
  const inside = (r) => r.left >= outer.left - 1 && r.right <= outer.right + 1
  const marker = document.querySelector('circle.price-last, circle.price-provisional')
  const money = [...document.querySelectorAll('.rh-sp-svg text.ax')]
    .filter((t) => (t.textContent || '').includes('$'))
  const mark = marker ? marker.getBoundingClientRect() : null
  const latest = mark ? mark.left - outer.left + box.scrollLeft : null
  const maxLeft = box.scrollWidth - box.clientWidth
  return {sw: box.scrollWidth, cw: box.clientWidth, left: Math.round(box.scrollLeft),
          pans: maxLeft > 1,
          marker_visible: !!mark && inside(mark),
          gutter_labels: money.map((t) => t.textContent),
          gutter_visible: money.length > 0 && money.every((t) => inside(t.getBoundingClientRect())),
          both_fit: latest !== null && maxLeft <= latest - box.clientWidth / 2}
})()"""


def run_case(context, label, state, surface, *, zoom=False):
    info = MANIFEST['states'][state]
    ticker, span = info['ticker'], info['span']
    case = Case(label)
    case.facts.update(state=state, surface=surface, ticker=ticker, span=span, zoom=zoom,
                      description=info['description'], expected=dict(
                          observations=info['observations'], segments=info['segments'],
                          multi=info['multi_point_segments'], single=info['single_point_segments']))
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda exc: errors.append(f'pageerror: {exc}'))
    page.on('console', lambda msg: errors.append(f'console.{msg.type}: {msg.text}')
            if msg.type == 'error' else None)
    mocks = Mocks(page, state)
    try:
        page.goto(f'{BASE}/radar/?span={span}&market=us#{surface}/{ticker}',
                  wait_until='domcontentloaded')
        page.wait_for_selector('.rh-sp-svg, .rh-sp-state[role=alert]', timeout=20000)
        page.wait_for_timeout(400)
        metrics = page.evaluate('({inner: innerWidth, outer: outerWidth, dpr: devicePixelRatio,'
                                ' scroll: document.documentElement.scrollWidth})')
        case.facts['metrics'] = metrics
        if zoom:
            case.check('real_zoom_in_effect',
                       metrics['dpr'] >= 1.9 and metrics['outer'] >= 1.8 * metrics['inner'], metrics)
        case.check('no_document_overflow', metrics['scroll'] <= metrics['inner'] + 1, metrics)
        case.check('new_chart_rendered', page.locator('.rh-sp-svg').count() == 1)
        case.check('old_chart_not_rendered', page.locator('svg.pxchart').count() == 0)

        geometry = page.evaluate(GEOMETRY)
        case.facts['geometry'] = geometry
        multi, single = info['multi_point_segments'], info['single_point_segments']
        case.check('one_line_per_multi_point_segment', geometry['lines'] == multi, geometry['lines'])
        case.check('one_area_per_multi_point_segment', geometry['areas'] == multi, geometry['areas'])
        case.check('a_dot_only_for_a_one_observation_segment', geometry['dots'] == single, geometry['dots'])
        case.check('exactly_one_latest_marker',
                   geometry['latest'] == (1 if info['observations'] else 0), geometry['latest'])
        case.check('no_dot_cloud', geometry['dots'] + geometry['latest'] <= single + 1,
                   {'dots': geometry['dots'], 'latest': geometry['latest']})
        expected_vertices = [s['points'] for s in info['segments'] if s['points'] > 1]
        case.check('a_line_vertex_per_actual_observation_and_no_more',
                   geometry['line_vertices'] == expected_vertices,
                   {'drawn': geometry['line_vertices'], 'observations': expected_vertices})
        case.check('the_area_adds_only_its_two_baseline_corners',
                   geometry['area_vertices'] == [n + 2 for n in expected_vertices],
                   geometry['area_vertices'])
        case.check('the_area_is_closed_and_filled_with_a_gradient',
                   (not multi) or (geometry['area_closed'] and geometry['area_fill_is_a_gradient']))
        if span == '1W' and geometry['areas']:
            # Five regular sessions inside a six-day window: a fill that
            # crossed a night would be several times wider than one session.
            case.check('no_fill_crosses_a_night',
                       max(geometry['area_spans']) < PLOT_R * 0.12, geometry['area_spans'])

        pan = page.evaluate(PAN)
        case.facts['pan'] = pan
        if pan['pans'] and info['observations']:
            # A panned chart that opens on empty after-hours hours, with the
            # whole session off screen to the left, is not a price chart.
            # (Where the drawing only just overflows, the latest observation
            # is already on screen at rest and no scroll is needed.)
            case.check('the_panned_chart_opens_on_the_latest_observation',
                       pan['marker_visible'], pan)
            # C2-2: the price axis and the window-end label live past the plot.
            # They are given up ONLY where showing them would hide the line.
            case.check('the_gutter_is_visible_at_rest_wherever_it_fits',
                       (not pan['both_fit']) or pan['gutter_visible'], pan)

        meta = page.locator('.rh-sp-meta').inner_text()
        summary = page.locator('.rh-sp-summary').inner_text()
        case.facts['meta'] = meta
        case.facts['summary'] = summary
        case.check('never_claims_real_time', not re.search(r'real.?time', meta + summary, re.I))
        case.check('no_return_or_direction_claim', not re.search(r'over this span|\d%', meta + summary))
        case.check('summary_names_this_company', summary.startswith(f'{ticker},'), summary[:120])
        if info['price_source'] == 'alpaca_sip':
            case.check('provenance_names_delayed_consolidated_sip',
                       'Alpaca consolidated SIP (delayed)' in meta, meta[:200])
            case.check('provenance_states_the_raw_basis', 'Adjustment basis raw' in meta)
            case.check('coverage_is_disclosed_not_implied',
                       f"{info['observations']} of {info['expected_intervals']} expected" in meta + summary,
                       summary[:200])
            case.check('summary_counts_the_hard_segments',
                       f"in {len(info['segments'])} segment" in summary, summary[:200])
        if info['price_source'] == 'finnhub':
            case.check('a_stored_fallback_says_so', 'fallback while the' in meta, meta[:200])
            case.check('a_stored_fallback_claims_no_expected_grid', 'expected' not in summary, summary[:200])
        if info['observations'] is None:
            # SVG text has no innerText, so read its text nodes.
            drawn = ' '.join(page.locator('.rh-sp-svg text').all_text_contents())
            case.check('an_absent_price_says_so_in_the_plot_and_the_provenance',
                       'No price observation inside this window' in drawn
                       and 'No price inside this window' in meta, {'drawn': drawn[:200], 'meta': meta[:200]})
            case.check('the_refusal_names_itself_without_a_credential',
                       'refused this process' in meta and not re.search(r'APCA|key|secret', meta),
                       meta[:200])

        # At rest, before the keyboard walk: a focus ring in every screenshot
        # would hide the edge of the drawing it is meant to show.
        case.facts['shot'] = shoot(page, label, zoom)
        if zoom or metrics['inner'] < 800:
            case.facts['shot_chart'] = shoot(page, f'{label}-chart', zoom, anchor='chart')
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
            case.check('keyboard_readout_reports_an_interval_and_its_counts',
                       all('mention' in text for text in (last, previous, first)) and last != previous,
                       case.facts['readouts'])
            focus = page.evaluate('getComputedStyle(document.activeElement).outlineStyle')
            case.check('focus_is_visible', focus not in ('none', ''), focus)
            case.facts['shot_focus'] = shoot(page, f'{label}-focus', zoom)
    except Exception as exc:  # noqa: BLE001 -- a raised check is a failure
        case.check('raised', False, f'{type(exc).__name__}: {exc}'[:400])
        case.facts['trace'] = traceback.format_exc()[-1500:]
    finally:
        case.check('no_page_errors', not [e for e in errors if e.startswith('pageerror')], errors[:5])
        case.facts['console_errors'] = errors[:10]
        case.check('no_unmocked_requests', not mocks.unexpected, mocks.unexpected[:5])
        page.close()
    return case


def run_two_charts_on_one_page(context, label):
    """Both surfaces exist in one document at once only across navigations, but
    the gradient id must still be unique per mounted chart: check that the
    fill a chart uses resolves to a gradient inside its own SVG."""
    case = Case(label)
    page = context.new_page()
    Mocks(page, 'sparse_1d')
    try:
        page.goto(f'{BASE}/radar/?span=1D&market=us#research/FT', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-sp-svg', timeout=20000)
        resolved = page.evaluate("""(() => {
            const svg = document.querySelector('.rh-sp-svg')
            const area = svg.querySelector('path.rh-sp-area')
            const id = (area.getAttribute('fill') || '').slice(5, -1)
            const target = svg.querySelector(`#${CSS.escape(id)}`)
            return {id, inside_its_own_svg: !!target,
                    stops: target ? [...target.querySelectorAll('stop')].map(
                      (s) => getComputedStyle(s).stopColor + ' @ ' + getComputedStyle(s).stopOpacity) : []}
        })()""")
        case.facts['gradient'] = resolved
        case.check('the_fill_resolves_inside_its_own_svg', resolved['inside_its_own_svg'], resolved)
        case.check('the_fill_fades_the_price_colour_to_nothing',
                   len(resolved['stops']) == 2 and resolved['stops'][1].endswith('@ 0'), resolved['stops'])
    except Exception as exc:  # noqa: BLE001
        case.check('raised', False, f'{type(exc).__name__}: {exc}'[:400])
    finally:
        page.close()


class AnyStateMocks(Mocks):
    """Serves whichever manifest state matches the requested ticker and span,
    so one page can switch charts the way a reader does."""

    def handle(self, route):
        url = urlsplit(route.request.url)
        path = url.path
        chart = re.fullmatch(r'/radar/api/ticker/([^/]+)/price-chart', path)
        if chart:
            query = parse_qs(url.query, keep_blank_values=True)
            ticker = unquote(chart.group(1))
            span = query.get('span', [''])[0]
            for name, info in MANIFEST['states'].items():
                if info['ticker'] == ticker and info['span'] == span:
                    self.state = name
                    self.chart_requests.append({'ticker': ticker, 'keys': sorted(query)})
                    return route.fulfill(json=load(info['file']))
        return super().handle(route)


def run_reader_scroll_case(context, label, width):
    """C2-3: the chart places itself ONCE per chart, then the reader owns it --
    including a reader sitting at exactly 0, the oldest history, which the old
    `scrollLeft === 0` sentinel could not tell apart from an unplaced chart."""
    case = Case(label)
    case.facts.update(state='sparse_1d', surface='research', width=width)
    page = context.new_page()
    mocks = AnyStateMocks(page, 'sparse_1d')
    read = "(() => { const b = document.querySelector('.rh-sp-wrap');"           " return Math.round(b.scrollLeft); })()"
    try:
        page.goto(f'{BASE}/radar/?span=1D&market=us#research/FT', wait_until='domcontentloaded')
        page.wait_for_selector('.rh-sp-svg', timeout=20000)
        page.wait_for_timeout(600)
        case.facts['opened_at'] = page.evaluate(read)
        case.check('a_new_chart_is_placed_once', case.facts['opened_at'] > 0, case.facts['opened_at'])

        def refresh_and_read(where):
            page.evaluate(f"document.querySelector('.rh-sp-wrap').scrollLeft = {where}")
            page.wait_for_timeout(120)
            # A refetch (new data object) and a resize both re-run the effect.
            page.set_viewport_size({'width': width + 1, 'height': 844})
            page.wait_for_timeout(700)
            back = page.evaluate(read)
            page.set_viewport_size({'width': width, 'height': 844})
            page.wait_for_timeout(300)
            return back

        # Half of whatever scroll range this width actually has: a position
        # past the end would be clamped by the browser and fire no event at all.
        into_history = page.evaluate(
            "(() => { const b = document.querySelector('.rh-sp-wrap');"
            " return Math.max(1, Math.round((b.scrollWidth - b.clientWidth) / 2)); })()")
        case.facts['scrolled_into_history_to'] = into_history
        middle = refresh_and_read(into_history)
        case.facts['after_refresh_from_middle'] = middle
        case.check('a_reader_scrolled_into_history_is_left_there', middle == into_history,
                   {'asked': into_history, 'after': middle})

        oldest = refresh_and_read(0)
        case.facts['after_refresh_from_zero'] = oldest
        case.check('a_reader_at_the_very_start_is_left_there', oldest == 0, oldest)

        # A different chart is a different question: it gets placed again.
        page.evaluate("location.hash = '#research/AAPL'")
        page.wait_for_function(
            "(() => { const s = document.querySelector('.rh-sp-summary');"
            " return s && s.textContent.startsWith('AAPL,'); })()", timeout=20000)
        page.wait_for_timeout(700)
        switched = page.evaluate(read)
        case.facts['after_switching_ticker'] = switched
        case.check('switching_chart_places_the_new_one', switched > 0, switched)
    except Exception as exc:  # noqa: BLE001
        case.check('raised', False, f'{type(exc).__name__}: {exc}'[:400])
        case.facts['trace'] = traceback.format_exc()[-1200:]
    finally:
        case.check('no_unmocked_requests', not mocks.unexpected, mocks.unexpected[:5])
        page.close()
    return case


SURFACES = ('research', 'chatter')
STATES = ('sparse_1d', 'dense_1d', 'week_1w', 'fallback_1d', 'unavailable_1w', 'chatter_gaps')


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
            for width, height in ((1200, 1000), (768, 1024), (390, 844)):
                context = browser.new_context(viewport={'width': width, 'height': height},
                                              has_touch=width < 768, is_mobile=width < 768,
                                              device_scale_factor=1)
                surfaces = SURFACES if width in (1200, 390) else ('research',)
                for state in STATES:
                    for surface in surfaces:
                        run_case(context, f'{state}-{surface}-{width}', state, surface)
                if width == 1200:
                    run_two_charts_on_one_page(context, 'gradient-identity-1200')
                if width in (1200, 390):
                    run_reader_scroll_case(context, f'reader-scroll-{width}', width)
                context.close()
            browser.close()

            with tempfile.TemporaryDirectory(prefix='md-sp-c1-zoom-') as profile:
                default = Path(profile) / 'Default'
                default.mkdir()
                (default / 'Preferences').write_text(json.dumps(
                    {'partition': {'default_zoom_level': {'x': ZOOM_LEVEL}}}), encoding='utf-8')
                context = playwright.chromium.launch_persistent_context(
                    profile, headless=False, no_viewport=True,
                    args=['--window-size=780,900', '--window-position=-2400,0'])
                try:
                    for state in ('sparse_1d', 'week_1w', 'fallback_1d'):
                        for surface in SURFACES:
                            run_case(context, f'zoom200-{state}-{surface}-390css', state, surface, zoom=True)
                finally:
                    for page in context.pages:
                        page.close()
                    context.close()
    finally:
        server.shutdown()
        server.server_close()
    RESULTS['seconds'] = round(time.time() - started, 1)
    RESULTS['port_free_after'] = port_is_free()
    RESULTS['checks'] = sum(len(case['checks']) for case in RESULTS['cases'].values())
    (HERE / 'results.json').write_text(json.dumps(RESULTS, indent=2), encoding='utf-8')
    summary = {label: (all(case['checks'].values()), len(case['checks']))
               for label, case in RESULTS['cases'].items()}
    print(json.dumps({'failures': RESULTS['failures'], 'server_404': SERVER_LOG,
                      'cases': summary, 'checks': RESULTS['checks'], 'seconds': RESULTS['seconds'],
                      'port_free_after': RESULTS['port_free_after']}, indent=1))
    return 1 if RESULTS['failures'] or SERVER_LOG else 0


if __name__ == '__main__':
    sys.exit(main())
