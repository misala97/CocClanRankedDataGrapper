"""HA1 actual-app acceptance (PLAN C15/C16) with Python Playwright.

    py -3.12 scratchpad/ha1/local_runtime.py serve 5041      # shell 1, gated
    py -3.12 scratchpad/ha1/preview_fixtures.py seed         # once, gated
    py -3.12 scratchpad/ha1/verify_preview.py 5041           # shell 2, gated
    py -3.12 scratchpad/ha1/preview_fixtures.py cleanup      # afterwards

CORRECTION-1 (2026-09-15): rewritten for REVIEW-1 R4/C11/C16; NOT executed.
Dated correction: implementation-evidence.md said this script refused
without RADAR_HA1_TARGET + RADAR_HA1_REGISTRY. The earlier version did not:
it refused only on missing credentials and never checked the target or the
listening server. That historical report is preserved; this version gates.

CORRECTION-2 (2026-09-15, harness only; NOT executed -- no DB, server or
browser was run):
- U1: runtime Git goes through local_runtime.git (per-command safe.directory).
- U2: search selection plus the canonical pin adds exactly ONE history entry
  (the pin replaces the ticker-only entry); Back returns to the pre-selection
  `#analysis`, Forward to the canonical URL; the URL must stay put after it
  settles (a repeated pin effect, U13, would show here).
- U3: C15 in the actual app with owned identities -- root/alias/legacy mounts
  and return link, signed-out redirects, valid `?t=`, a valid hash over `t`,
  invalid-hash fallback, filter-only bookmark with refresh, canonical Analysis
  link, and NO /radar/api/board request while Analysis stays active for longer
  than the hub's minute read and 120 s stale re-ask, with a positive control
  on leaving; board requests made while the shell boots are recorded, not
  failed.
- U6: contrast fails empty required selectors, unsupported colours and
  unverifiable backgrounds, composites alpha against the real ancestor
  background, and requires evaluated text pairs at 4.5:1 AND meaningful
  graphics pairs at 3:1; a case that evaluated no check fails.
- U8: the runtime record's source/build fingerprint must equal a fresh one,
  before and after the run; drift requires a deliberate rebuild/restart.
- U9: real taps and scroll-box reachability on touch widths, usable 200%
  zoom (select a day, change the range), rendered range and request after
  refresh, positive adjacent-price runs with a weekend break, day-button to
  plotted-column alignment, skip link / Tab order / Escape, partial bars
  patterned (SPEC section 3); an exception in a shared block is attributed to
  every case in it; unsupported checks are failures.

Refusals, in order, before anything is logged into:
1. local_runtime.gate(): target + registry, same rules as the server. No app
   import, no database connection, no network.
2. The port is not 5021/5033, and a runtime identity record exists for it.
3. That record names this candidate root, its current branch and HEAD, the
   gated target and registry, a live pid and the current source/build
   fingerprint.
4. An unauthenticated GET /login on 127.0.0.1:<port> answers with the
   record's nonce: the listener IS that gated process.
5. The owned preview fixture manifest names the same target; credentials for
   the operator's admin and the owned non-admin account are present.

Then every check is an assertion recorded per case (ha1_harness
.ACCEPTANCE_CASES); an unrecorded or zero-check case fails; the process exits
1 on any failure. Screenshots go to radar-design/artifacts/ha1/preview/ and
must then be VIEWED, not merely counted. Touch emulation is not a physical
device; 200% zoom is emulated by halving the CSS viewport at device scale 2.
Synthetic local data only.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ha1_harness as harness  # noqa: E402
import local_runtime  # noqa: E402

OUT = local_runtime.RUNTIME_DIR.parent / 'preview'
MANIFEST = local_runtime.RUNTIME_DIR / 'preview-fixtures.json'
VIEWPORTS = {'1440': (1440, 1000), '1920': (1920, 1080), '768': (768, 1024),
             '390': (390, 844), '320': (320, 844)}
NARROW = ('390', '320')
COMPANY_API = '**/radar/api/analysis/company/**'
DAY_GROUP = '[role=group][aria-label="Select a day"]'
MAIN = 'main[aria-label="Analysis"]'
CANONICAL = '/^#analysis\\/[A-Z0-9]+\\/\\d+\\/\\d+$/.test(location.hash)'
#: Longer than the hub board's one-minute re-read and its 120 s stale re-ask
#: (static/radar/src/hub/queries.ts), so a recurring board request behind an
#: active Analysis page would land inside the window.
BOARD_QUIET_MS = 130_000
ALIGN_TOLERANCE_PX = 2.0

TEXT_CONTRAST = (
    ('main h1', 'color'), ('.rh-an-identity dt', 'color'), ('.rh-an-identity dd', 'color'),
    ('.rh-an-list li', 'color'), ('.rh-an-caption', 'color'), ('.rh-an-table td', 'color'),
    ('.rh-an-dayfacts', 'color'), ('svg .rh-an-axis', 'fill'), ('svg .rh-an-value', 'fill'),
)
GRAPHIC_CONTRAST_TYPICAL = (
    ('svg.price circle[data-state="observed"]', 'fill'),
    ('svg.counts rect.rh-an-fill:not(.partial)', 'fill'),
    ('svg.counts rect.rh-an-fill.partial', 'stroke'),
    ('svg.counts rect.rh-an-gap', 'stroke'),
)
GRAPHIC_CONTRAST_LINES = (
    ('svg.price polyline.rh-an-line', 'stroke'),
    ('svg.price line[data-state="missing-closed"]', 'stroke'),
)

CONTRAST_JS = """(pairs) => pairs.map(([selector, property]) => {
  const visible = Array.from(document.querySelectorAll(selector)).filter((el) => {
    const r = el.getBoundingClientRect(); return r.width > 0 || r.height > 0 })
  const describe = (node) => node.tagName.toLowerCase() + (typeof node.className === 'string'
    && node.className.trim() ? '.' + node.className.trim().split(/\\s+/).join('.') : '')
  return {selector, property, matched: visible.length, pairs: visible.slice(0, 3).map((el) => {
    const layers = []
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      const style = getComputedStyle(node)
      layers.push({node: describe(node), color: style.backgroundColor,
                   image: style.backgroundImage !== 'none'})
    }
    return {value: getComputedStyle(el)[property], layers}
  })}
})"""

ALIGN_JS = """() => {
  const center = (el) => { const r = el.getBoundingClientRect(); return r.left + r.width / 2 }
  return {
    buttons: Array.from(document.querySelectorAll('[role=group][aria-label="Select a day"] button')).map(center),
    points: Array.from(document.querySelectorAll('svg.price g.rh-an-point')).map(center),
    bars: Array.from(document.querySelectorAll('svg.counts g.rh-an-bar')).map(center),
  }
}"""

#: FINAL-UI-CHECK (F1): whether each range input can show its whole value.
#: scrollWidth alone is not trusted: the value's rendered text width (canvas
#: measureText with the input's computed font) must also fit the content box.
DATE_CLIP_JS = """() => Array.from(document.querySelectorAll('form.rh-an-range input')).map((el) => {
  const style = getComputedStyle(el)
  const context = document.createElement('canvas').getContext('2d')
  context.font = style.font || `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
  if (style.letterSpacing && style.letterSpacing !== 'normal') context.letterSpacing = style.letterSpacing
  const text = context.measureText(el.value || el.placeholder).width
  const content = el.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
  const box = el.getBoundingClientRect()
  return {name: el.name, value: el.value, text: Math.round(text * 10) / 10, content: Math.round(content * 10) / 10,
          clientWidth: el.clientWidth, scrollWidth: el.scrollWidth, width: Math.round(box.width),
          height: Math.round(box.height),
          clipped: el.scrollWidth > el.clientWidth || text > content + 0.5}
})"""

FOCUS_JS = """() => {
  const el = document.activeElement
  if (!el || el === document.body) return 'body'
  if (el.name === 'analysis_from' || el.name === 'analysis_to') return el.name
  if (el.closest('[role=group][aria-label="Select a day"]')) return 'day'
  if (el.type === 'submit' && el.closest('form.rh-an-range')) return 'submit'
  if (el.classList.contains('rh-skip')) return 'skip'
  if (el.id === 'rh-main') return 'main'
  return el.tagName.toLowerCase() + ':' + (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 24)
}"""


def progress(message):
    """LOCAL-QA: an operator progress line, flushed so a long run is observable."""
    print(f'[{dt.datetime.now().strftime("%H:%M:%S")}] {message}', flush=True)


def _pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if os.name == 'nt':
        listing = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                                 capture_output=True, text=True).stdout
        return re.search(rf'\b{pid}\b', listing) is not None
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def preflight(argv, env=None):
    """Gates 1-5. Returns (port, manifest, credentials, record fingerprint)
    or raises SystemExit."""
    values = os.environ if env is None else env
    _, _, _, target, registry = local_runtime.gate(values)
    port = int(argv[1]) if len(argv) > 1 else 5041
    if port in local_runtime.REFUSED_PORTS:
        raise SystemExit(f'port {port} belongs to another preview')
    path = local_runtime.runtime_path(port)
    record = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    header = None
    if isinstance(record, dict):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/login', timeout=5) as response:
                header = response.headers.get(local_runtime.RUNTIME_HEADER)
        except OSError:
            header = None
    fingerprint = harness.source_fingerprint(local_runtime.CANDIDATE) if isinstance(record, dict) else None
    failures = harness.preview_identity_failures(
        record, target=target, registry=registry, root=local_runtime.CANDIDATE,
        branch=local_runtime.git('rev-parse', '--abbrev-ref', 'HEAD'),
        head=local_runtime.git('rev-parse', 'HEAD'), port=port, header_nonce=header,
        pid_alive=isinstance(record, dict) and _pid_alive(record.get('pid')),
        fingerprint=fingerprint)
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else None
    if not isinstance(manifest, dict):
        failures.append('no owned preview fixture manifest: run preview_fixtures.py seed first')
    elif manifest.get('target') != target:
        failures.append(f'the fixture manifest belongs to {manifest.get("target")!r}, not {target!r}')
    elif 'lines' not in (manifest.get('cases') or {}):
        failures.append('the fixture manifest predates CORRECTION-2 (no lines case): cleanup and seed again')
    credentials = {'admin': (values.get('RADAR_HA1_USER'), values.get('RADAR_HA1_PASSWORD')),
                   'plain': ((manifest or {}).get('plain_user'), values.get('RADAR_HA1_PLAIN_PASSWORD'))}
    for role, (user, password) in credentials.items():
        if not user or not password:
            failures.append(f'missing {role} credentials')
    if failures:
        raise SystemExit('preview identity not established; nothing was logged into:\n- '
                         + '\n- '.join(failures))
    return port, manifest, credentials, record['fingerprint']


def link(base, manifest, name, *, instrument_key='instrument_id', start=None, end=None,
         query='market=us', ticker_only=False):
    info = manifest['cases'][name]
    window = info.get('window') or manifest['window']
    start = window['from'] if start is None else start
    end = window['to'] if end is None else end
    target = (f'#analysis/{info["symbol"]}' if ticker_only else
              f'#analysis/{info["symbol"]}/{info["company_id"]}/{info[instrument_key]}')
    return f'{base}/radar/?{query}&analysis_from={start}&analysis_to={end}{target}'


def same_address(left, right):
    a, b = urlsplit(left), urlsplit(right)
    return (a.path, a.fragment, parse_qs(a.query)) == (b.path, b.fragment, parse_qs(b.query))


def login(page, base, user, password):
    page.goto(f'{base}/login')
    page.fill('input[name=username]', user)
    page.fill('input[name=password]', password)
    page.click('button[type=submit], input[type=submit]')
    page.wait_for_load_state('networkidle')


def no_overflow(page):
    return page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')


def small_targets(page):
    return page.evaluate("""(main) => Array.from(document.querySelectorAll(
        `${main} button, ${main} input, ${main} a`))
      .filter((el) => el.offsetParent !== null)
      .map((el) => { const r = el.getBoundingClientRect();
        return {text: (el.getAttribute('aria-label') || el.textContent || el.name || '').trim().slice(0, 40),
                w: Math.round(r.width), h: Math.round(r.height)} })
      .filter((t) => t.w < 44 || t.h < 44)""", MAIN)


def contrast_checks(c, page, pairs, *, minimum, kind):
    samples = page.evaluate(CONTRAST_JS, [list(pair) for pair in pairs])
    problems, evaluated = harness.contrast_failures(samples, minimum=minimum, kind=kind)
    c.facts.setdefault(kind, []).extend(evaluated)
    for problem in problems:
        c.check(False, problem)
    c.check(bool(evaluated), f'{kind}: no pair evaluated')


def screenshot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / f'{name}.png'), full_page=True)


def wait_ready(page):
    page.wait_for_selector(f'{DAY_GROUP}, {MAIN} [role=alert]', timeout=harness.BROWSER_TIMEOUT_MS + 2000)


def body_has(page, text, timeout=15000):
    try:
        page.wait_for_function('(text) => document.body.innerText.includes(text)', arg=text, timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 -- a missing text is a failed check, not a crash
        return False


def company_requests(page):
    seen = []
    page.on('request', lambda request: seen.append(request.url)
            if '/radar/api/analysis/company/' in request.url else None)
    return seen


def c15_routes(page, base, manifest, results, label, requests):
    """U3: C15 in the actual app with the owned fixture identity only."""
    typical = manifest['cases']['typical']
    symbol = typical['symbol']
    with harness.case(results, 'c15_root_overview_mount', label) as c:
        page.goto(f'{base}/radar/')
        page.wait_for_selector('main[aria-label="Overview"]')
        c.check(page.locator('#radar-hub-data').count() == 1, 'root does not mount the hub')
        c.check(page.locator('#radar-data').count() == 0, 'root mounts the legacy board')
    with harness.case(results, 'c15_hub_alias_mount', label) as c:
        page.goto(f'{base}/radar/hub/')
        page.wait_for_selector('main[aria-label="Overview"]')
        c.check(urlsplit(page.url).path == '/radar/hub/', f'alias redirected to {page.url}')
        c.check(page.locator('#radar-hub-data').count() == 1, 'alias does not mount the hub')
    with harness.case(results, 'c15_legacy_mount_and_return', label) as c:
        page.goto(f'{base}/radar/legacy/?market=de&window=12')
        c.check(page.locator('#radar-data').count() == 1, 'legacy route does not mount the board')
        c.check(page.locator('#radar-hub-data').count() == 0, 'legacy route mounts the hub')
        back = page.get_by_role('link', name='Return to Radar hub')
        href = back.get_attribute('href') or ''
        c.check(href.startswith('/radar/?') and 'market=de' in href, f'return link is {href!r}')
        back.click()
        page.wait_for_selector('main[aria-label="Human Chatter"]')
        c.check('market=de' in page.evaluate('location.search'), 'return link lost the board query')
    with harness.case(results, 'c15_valid_t_bookmark', label) as c:
        page.goto(f'{base}/radar/?t={symbol}&market=us')
        page.wait_for_selector('main[aria-label="Human Chatter"]')
        c.check(body_has(page, symbol), f'the ?t={symbol} bookmark did not open that company')
    with harness.case(results, 'c15_valid_hash_overrides_t', label) as c:
        page.goto(f'{base}/radar/?t={symbol}&market=de#overview')
        page.wait_for_selector('main[aria-label="Overview"]')
        c.check(page.url.endswith('#overview'), f'a valid hash did not win over t: {page.url}')
    with harness.case(results, 'c15_invalid_hash_fallback', label) as c:
        page.goto(f'{base}/radar/?t={symbol}#nonsense')
        page.wait_for_selector('main[aria-label="Human Chatter"]')
        c.check(body_has(page, symbol), 'an invalid hash did not fall back to the valid t')
    with harness.case(results, 'c15_filter_only_bookmark', label) as c:
        page.goto(f'{base}/radar/?market=de&window=24')
        page.wait_for_selector('main[aria-label="Human Chatter"]')
        # LOCAL-QA: a parsed key, not the substring 't=' (it matched inside the
        # hub's normalized 'segment=' in run2).
        c.check('t' not in parse_qs(urlsplit(page.url).query), 'a company was invented for a filter-only link')
        page.reload()
        page.wait_for_selector('main[aria-label="Human Chatter"]')
        c.check('market=de' in page.evaluate('location.search'), 'refresh lost the filter context')
    with harness.case(results, 'c15_canonical_analysis_link', label) as c:
        requests.clear()
        address = link(base, manifest, 'typical')
        page.goto(address)
        wait_ready(page)
        c.check(same_address(page.url, address), f'the canonical link was rewritten: {page.url}')
        c.check(symbol in (page.text_content('.rh-an-identity') or ''), 'identity strip does not name the link')
        window = manifest['window']
        c.check(any(f'/company/{typical["company_id"]}?' in u and f'instrument_id={typical["instrument_id"]}' in u
                    and f'from={window["from"]}' in u and f'to={window["to"]}' in u for u in requests),
                f'no request for exactly the linked identity and window: {requests}')
        nav = page.locator('a.rh-navlink[aria-current="page"]')
        c.check(nav.count() == 1 and 'Analysis' in (nav.first.text_content() or ''), 'Analysis is not the current nav item')
        legacy = page.locator('a.rh-navlink', has_text='Legacy Radar')
        c.check(legacy.count() == 1 and (legacy.first.get_attribute('href') or '').startswith('/radar/legacy/'),
                'no Legacy Radar link from Analysis')


def run(port, manifest, credentials, record_fingerprint):
    from playwright.sync_api import sync_playwright

    base = f'http://127.0.0.1:{port}'
    results = {'gate_identity': {'failures': [], 'checks': 5,
                                 'facts': {'port': port, 'fingerprint': record_fingerprint['digest']}}}
    admin, plain = credentials['admin'], credentials['plain']
    typical = manifest['cases']['typical']
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        with harness.case(results, 'c15_signed_out_redirects') as c:
            context = browser.new_context()
            company = (f'/radar/api/analysis/company/{typical["company_id"]}?instrument_id='
                       f'{typical["instrument_id"]}&from={manifest["window"]["from"]}&to={manifest["window"]["to"]}')
            for path in ('/radar/', '/radar/hub/', '/radar/legacy/',
                         f'/radar/api/analysis/resolve?ticker={typical["symbol"]}', company):
                response = context.request.get(f'{base}{path}', max_redirects=0)
                location = response.headers.get('location', '')
                c.check(response.status in (301, 302, 303, 307, 308) and '/login' in location,
                        f'signed out {path}: {response.status} {location!r}')
            context.close()

        for label, (width, height) in VIEWPORTS.items():
            progress(f'viewport {label} started')
            narrow = label in NARROW
            context = browser.new_context(viewport={'width': width, 'height': height}, has_touch=narrow)
            page = context.new_page()
            requests = company_requests(page)
            login(page, base, *admin)

            with harness.case(results, 'empty_analysis', label) as c:
                page.goto(f'{base}/radar/?market=de&window=24#analysis')
                page.wait_for_selector(MAIN)
                c.check('Explore' in (page.text_content('main h1') or ''), 'heading is not Explore')
                c.check(page.is_visible(f'{MAIN} >> text=US primary · USD'), 'US primary · USD not visible')
                screenshot(page, f'empty-{label}')

            # U2: selection pushes once, the pin replaces; Back is pre-selection Analysis.
            with harness.cases(results, ('resolve_pin_replace', 'de_entry_us_label',
                                         'c15_back_to_pre_selection_analysis'), label) as (c, de, back):
                pre_selection = page.url
                length = page.evaluate('history.length')
                c.check(page.is_visible('#rh-search-input'), 'global search is not reachable on this width')
                page.fill('#rh-search-input', typical['symbol'])
                page.click('[role=option] button')
                page.wait_for_function(CANONICAL)
                wait_ready(page)
                canonical = page.url
                page.wait_for_timeout(1500)
                grown = page.evaluate('history.length')
                c.check(grown == length + 1,
                        f'selection plus pin must add exactly one history entry: {length} -> {grown}')
                c.check(page.url == canonical, f'the pinned address changed again after settling: {page.url}')
                c.check('analysis_from=' in page.evaluate('location.search'), 'no explicit dates after pinning')
                de.check('market=de' in page.evaluate('location.search'), 'DE board context dropped')
                de.check('US primary · USD · all retained sources' in (page.text_content('.rh-an-identity') or ''),
                         'identity strip does not state US primary · USD')
                page.go_back()
                page.wait_for_function(f'!({CANONICAL})')
                page.wait_for_selector(MAIN)
                hash_after_back = page.evaluate('location.hash')
                back.check(hash_after_back == '#analysis',
                           f'Back landed on {hash_after_back!r}, not the pre-selection #analysis '
                           '(a ticker-only entry means the pin pushed instead of replacing)')
                back.check(same_address(page.url, pre_selection), f'Back address {page.url} != {pre_selection}')
                page.go_forward()
                page.wait_for_function(CANONICAL)
                back.check(page.url == canonical, f'Forward did not return to the canonical address: {page.url}')

            with harness.cases(results, (f'viewport_{label}', 'no_document_overflow'), label) as (c, overflow):
                page.goto(link(base, manifest, 'typical'))
                wait_ready(page)
                c.check(page.is_visible(DAY_GROUP), 'day selector not visible')
                c.check(page.is_visible('.rh-an-rail, .rh-an-identity'), 'identity/provenance missing')
                overflow.check(no_overflow(page), 'document scrolls horizontally')
                dates = page.evaluate(DATE_CLIP_JS)
                c.facts['date_inputs'] = dates
                c.check(len(dates) == 2, f'{len(dates)} range inputs, expected 2')
                c.check(all(len(item['value']) == 10 and not item['clipped'] for item in dates),
                        f'a range input clips its YYYY-MM-DD value: {dates}')
                screenshot(page, f'typical-{label}')

            if label in ('1440', '390'):
                with harness.case(results, 'chart_control_alignment', label) as c:
                    geometry = page.evaluate(ALIGN_JS)
                    c.facts['centers'] = geometry
                    buttons, points, bars = geometry['buttons'], geometry['points'], geometry['bars']
                    c.check(len(buttons) == len(points) == len(bars) == 7,
                            f'{len(buttons)} buttons, {len(points)} price columns, {len(bars)} count columns')
                    for index, (button, point, bar) in enumerate(zip(buttons, points, bars)):
                        c.check(abs(button - point) <= ALIGN_TOLERANCE_PX,
                                f'day {index}: button centre {button:.1f} vs price column {point:.1f}')
                        c.check(abs(button - bar) <= ALIGN_TOLERANCE_PX,
                                f'day {index}: button centre {button:.1f} vs count column {bar:.1f}')

            if narrow:
                with harness.case(results, 'touch_targets_44', label) as c:
                    small = small_targets(page)
                    c.facts['small'] = small
                    c.check(not small, f'{len(small)} control(s) under 44px')
                with harness.case(results, 'us_primary_usd_visible_mobile', label) as c:
                    c.check(page.is_visible(f'{MAIN} .rh-an-scope'), 'US primary · USD scope not visible in Analysis')
                with harness.case(results, 'touch_select_and_scroll_reach', label) as c:
                    box = page.locator('.rh-an-plotscroll')
                    c.facts['scrollbox'] = box.evaluate(
                        '(el) => ({scrollWidth: el.scrollWidth, clientWidth: el.clientWidth})')
                    buttons = page.locator(f'{DAY_GROUP} button')
                    count = buttons.count()
                    c.check(count == 7, f'{count} day buttons, expected 7')
                    headings = []
                    for index in (count - 1, 0):
                        button = buttons.nth(index)
                        button.scroll_into_view_if_needed()
                        where = button.evaluate("""(el) => { const b = el.getBoundingClientRect();
                          const s = el.closest('.rh-an-plotscroll').getBoundingClientRect();
                          return {left: b.left, right: b.right, boxLeft: s.left, boxRight: s.right,
                                  viewport: document.documentElement.clientWidth} }""")
                        c.check(where['left'] >= where['boxLeft'] - 1 and where['right'] <= where['boxRight'] + 1,
                                f'day {index} is clipped by the scroll box: {where}')
                        c.check(where['left'] >= -1 and where['right'] <= where['viewport'] + 1,
                                f'day {index} is outside the viewport: {where}')
                        button.tap()
                        c.check(button.get_attribute('aria-pressed') == 'true', f'a tap on day {index} did not select it')
                        headings.append(page.text_content('.rh-an-detail h2'))
                    c.check(len(headings) == 2 and headings[0] != headings[1],
                            f'the selected-day detail did not follow the taps: {headings}')
                with harness.case(results, 'menu_escape', label) as c:
                    menu = page.locator('button.rh-menu')
                    if not menu.is_visible():
                        c.unsupported('the navigation menu button is not visible at this width')
                    else:
                        menu.click()
                        c.check(menu.get_attribute('aria-expanded') == 'true', 'the menu did not open')
                        page.keyboard.press('Escape')
                        c.check(menu.get_attribute('aria-expanded') == 'false', 'Escape did not close the menu')
                        c.check(page.evaluate('document.activeElement.classList.contains("rh-menu")'),
                                'Escape did not return focus to the menu button')

            if label == '1440':
                with harness.cases(results, ('keyboard_days', 'focus_visible')) as (c, focus):
                    page.focus(f'{DAY_GROUP} button[tabindex="0"]')
                    before = page.text_content('.rh-an-detail h2')
                    page.keyboard.press('ArrowLeft')
                    c.check(page.evaluate('document.activeElement.getAttribute("aria-pressed")') == 'true',
                            'arrow did not move the pressed day')
                    c.check(page.text_content('.rh-an-detail h2') != before, 'detail did not follow the keyboard')
                    style = page.evaluate('(() => { const s = getComputedStyle(document.activeElement);'
                                          ' return [s.outlineStyle, s.boxShadow] })()')
                    focus.check(style[0] != 'none' or style[1] != 'none', f'no visible focus: {style}')
                    screenshot(page, 'keyboard-1440')
                with harness.case(results, 'keyboard_table') as c:
                    button = page.locator('.rh-an-table th[scope=row] button').first
                    button.focus()
                    page.keyboard.press('Enter')
                    c.check((button.text_content() or '') in (page.text_content('.rh-an-detail h2') or ''),
                            'Enter on a table day did not select it')
                with harness.case(results, 'contrast_text') as c:
                    contrast_checks(c, page, TEXT_CONTRAST, minimum=harness.TEXT_CONTRAST_MIN, kind='text')
                with harness.case(results, 'contrast_graphics') as c:
                    contrast_checks(c, page, GRAPHIC_CONTRAST_TYPICAL, minimum=harness.GRAPHIC_CONTRAST_MIN,
                                    kind='graphics')
                    page.goto(link(base, manifest, 'lines'))
                    wait_ready(page)
                    contrast_checks(c, page, GRAPHIC_CONTRAST_LINES, minimum=harness.GRAPHIC_CONTRAST_MIN,
                                    kind='graphics')
                with harness.case(results, 'price_line_runs') as c:
                    info = manifest['cases']['lines']
                    page.goto(link(base, manifest, 'lines'))
                    wait_ready(page)
                    expected = sorted(','.join(map(str, run)) for run in info['expected_runs'])
                    closed = set(info['closed_indexes'])
                    c.check(bool(expected), 'the lines fixture has no adjacent observed pair: not a positive check')
                    c.check(bool(closed), 'the lines fixture has no closed date inside: no break is proven')
                    drawn = page.eval_on_selector_all(
                        'svg.price polyline.rh-an-line',
                        'els => els.map(e => [e.getAttribute("data-run"), e.getAttribute("points").trim().split(/\\s+/).length])')
                    c.facts['drawn'] = drawn
                    c.check(sorted(run for run, _ in drawn) == expected, f'drawn runs {drawn}, expected {expected}')
                    for run, points in drawn:
                        indexes = [int(value) for value in run.split(',')]
                        c.check(points == len(indexes), f'run {run} has {points} points')
                        c.check(not closed & set(indexes) and indexes == list(range(indexes[0], indexes[-1] + 1)),
                                f'run {run} crosses a date without a close')
                    screenshot(page, 'lines-1440')
                with harness.case(results, 'skip_link_and_tab_order') as c:
                    # LOCAL-QA: a fresh tab, so the first Tab starts at the
                    # document and not at the focus navigation point left by
                    # the earlier keyboard cases (blur() does not reset it).
                    tab_page = context.new_page()
                    try:
                        tab_page.goto(link(base, manifest, 'typical'))
                        wait_ready(tab_page)
                        c.check(tab_page.evaluate(FOCUS_JS) == 'body',
                                f'focus moved on load: {tab_page.evaluate(FOCUS_JS)!r}')
                        tab_page.keyboard.press('Tab')
                        c.check(tab_page.evaluate(FOCUS_JS) == 'skip',
                                f'the first Tab stop is {tab_page.evaluate(FOCUS_JS)!r}')
                        address = tab_page.url
                        tab_page.keyboard.press('Enter')
                        c.check(tab_page.evaluate(FOCUS_JS) == 'main', 'the skip link did not focus the page')
                        c.check(tab_page.url == address, f'the skip link changed the route: {tab_page.url}')
                        order = []
                        for _ in range(60):
                            tab_page.keyboard.press('Tab')
                            order.append(tab_page.evaluate(FOCUS_JS))
                            if order[-1] == 'day':
                                break
                    finally:
                        tab_page.close()
                    c.facts['tab_order'] = order
                    positions = [order.index(name) if name in order else None
                                 for name in ('analysis_from', 'analysis_to', 'submit', 'day')]
                    c.check(None not in positions and positions == sorted(positions),
                            f'Tab order from the page is not range controls then day buttons: {order}')
                with harness.case(results, 'explicit_range_push_back_refresh') as c:
                    window = manifest['window']
                    page.goto(link(base, manifest, 'typical'))
                    wait_ready(page)
                    first = page.url
                    page.fill('input[name=analysis_from]', window['from'])
                    page.fill('input[name=analysis_to]', window['from'])
                    page.click('button:has-text("Show these days")')
                    page.wait_for_function('location.search.includes("analysis_to=' + window['from'] + '")')
                    wait_ready(page)
                    c.check(any(f'to={window["from"]}' in url for url in requests), 'no request for the new window')
                    page.go_back()
                    page.wait_for_function(f'location.href === {json.dumps(first)}')
                    query = parse_qs(urlsplit(first).query)
                    start, end = query['analysis_from'][0], query['analysis_to'][0]
                    requests.clear()
                    page.reload()
                    wait_ready(page)
                    c.check(page.url == first, 'refresh did not restore the exact address')
                    c.check(page.input_value('input[name=analysis_from]') == start
                            and page.input_value('input[name=analysis_to]') == end,
                            'refresh did not render the restored range in the controls')
                    c.check(any(f'from={start}' in url and f'to={end}' in url for url in requests),
                            f'refresh did not request the restored window: {requests}')
                    days =(dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days + 1
                    c.check(page.locator(f'{DAY_GROUP} button').count() == days,
                            f'refresh rendered {page.locator(f"{DAY_GROUP} button").count()} days, asked {days}')
                with harness.case(results, 'back_restores_board') as c:
                    page.goto(f'{base}/radar/?market=de&window=24#chatter')
                    page.click('a.rh-navlink:has-text("Analysis")')
                    page.wait_for_selector(MAIN)
                    page.go_back()
                    page.wait_for_selector('main[aria-label="Human Chatter"]')
                    c.check('market=de' in page.evaluate('location.search'), 'Back lost the board context')
                with harness.case(results, 'c15_no_board_poll_on_analysis') as c:
                    board = []

                    def on_board(request):
                        if '/radar/api/board' in request.url:
                            board.append(request.url)
                    page.on('request', on_board)
                    try:
                        page.goto(link(base, manifest, 'typical'))
                        wait_ready(page)
                        c.facts['bootstrap_board_requests'] = list(board)  # permitted, recorded
                        board.clear()
                        waited = 0
                        for segment in harness.quiet_segments(BOARD_QUIET_MS):
                            page.wait_for_timeout(segment)
                            waited += segment
                            progress(f'board-quiet window {waited // 1000}/{BOARD_QUIET_MS // 1000} s, '
                                     f'{len(board)} board request(s) so far')
                        c.check(page.is_visible(DAY_GROUP), 'Analysis did not stay the active page')
                        c.check(not board, f'{len(board)} board request(s) while Analysis was active: {board}')
                        page.get_by_role('link', name=re.compile(r'human chatter', re.I)).first.click()
                        page.wait_for_selector('main[aria-label="Human Chatter"]')
                        deadline = time.monotonic() + 15
                        while not board and time.monotonic() < deadline:
                            page.wait_for_timeout(250)
                        c.check(bool(board), 'no board request after leaving Analysis: the listener is unproven, '
                                             'so the quiet window proves nothing')
                    finally:
                        page.remove_listener('request', on_board)

            if label in ('1440', '390'):
                c15_routes(page, base, manifest, results, label, requests)
                with harness.case(results, 'invalid_range_pinned', label) as c:
                    requests.clear()
                    page.goto(link(base, manifest, 'typical', start='2026-13-07'))
                    page.wait_for_selector('#rh-an-rangeproblem')
                    page.wait_for_timeout(1000)
                    c.check(page.input_value('input[name=analysis_from]') == '2026-13-07', 'raw date not editable')
                    c.check('2026-13-07' in (page.text_content('#rh-an-rangeproblem') or ''), 'raw date not echoed')
                    c.check(not requests, f'fetched for an invalid window: {requests}')
                    screenshot(page, f'invalid-pinned-{label}')
                with harness.case(results, 'invalid_range_ticker_only', label) as c:
                    requests.clear()
                    page.goto(link(base, manifest, 'typical', start='2026-13-07', ticker_only=True))
                    page.wait_for_function(CANONICAL)
                    page.wait_for_selector('#rh-an-rangeproblem')
                    page.wait_for_timeout(1000)
                    c.check('analysis_from=2026-13-07' in page.evaluate('location.search'), 'raw date lost on pinning')
                    c.check(not requests, f'fetched a guessed window: {requests}')
                expectations = {
                    'one_close': ('one_close', ['1 of 7 days observed']),
                    'no_close_no_chatter': ('no_data', ['No usable close in this window',
                                                        'No retained bucket in this window']),
                    'partial_truncated_zero': ('partial', ['coverage incomplete', '0 observed']),
                    'config_transition': ('config', ['config changed']),
                    'overlap': ('overlap', ['source overlap']),
                    'identity_boundary': ('identity', ['before the company record',
                                                       'only before the company record']),
                    'regime_change': ('regime', ['Source or basis changed inside the window']),
                    'invalid_row_closed_day_close': ('invalid', ['retained row unusable', 'modeled_closed day']),
                    'excluded_rows': ('excluded', ['off the 15-minute grid']),
                    'limit_503': ('limit', ['The read exceeded its bounds.']),
                }
                for case_name, (fixture, texts) in expectations.items():
                    with harness.case(results, case_name, label) as c:
                        page.goto(link(base, manifest, fixture))
                        wait_ready(page)
                        if case_name == 'config_transition':
                            page.click(f'{DAY_GROUP} button:nth-child(2)')
                        if case_name == 'overlap':
                            page.click(f'{DAY_GROUP} button:nth-child(4)')
                        body = page.text_content(MAIN) or ''
                        for text in texts:
                            c.check(text in body, f'missing {text!r}')
                        if case_name == 'regime_change':
                            c.check(page.locator('polyline.rh-an-line').count() == 0,
                                    'a line crosses a regime boundary')
                        if case_name == 'partial_truncated_zero':
                            fills = page.eval_on_selector_all('svg.counts rect.rh-an-fill.partial',
                                                              'els => els.map(e => getComputedStyle(e).fill)')
                            c.facts['partial_fills'] = fills
                            c.check(bool(fills) and all('url(' in fill for fill in fills),
                                    f'partial bars are not patterned (SPEC section 3 pattern+text): {fills}')
                        c.check(no_overflow(page), 'document scrolls horizontally')
                        screenshot(page, f'{case_name}-{label}')
                with harness.case(results, 'stale_link_409', label) as c:
                    page.goto(link(base, manifest, 'stale', instrument_key='stale_instrument_id'))
                    wait_ready(page)
                    c.check("no longer matches today's mapping" in (page.text_content(MAIN) or ''), 'no 409 notice')
                    screenshot(page, f'stale-{label}')
                with harness.case(results, 'ineligible_422', label) as c:
                    page.goto(link(base, manifest, 'ineligible', ticker_only=True))
                    page.wait_for_selector(f'{MAIN} [role=alert]')
                    c.check('no native-USD US primary' in (page.text_content(MAIN) or ''), 'no 422 notice')
                with harness.case(results, 'ambiguous_resolve_409', label) as c:
                    page.goto(link(base, manifest, 'ambiguous', ticker_only=True))
                    page.wait_for_selector(f'{MAIN} [role=alert]')
                    c.check('ambiguous_primary' in (page.text_content(MAIN) or ''), 'no ambiguity notice')

            if label == '1440':
                # LOCAL-QA: every injected UI state runs in a FRESH tab. In the
                # shared tab the earlier cases had already cached these keys
                # (60 s staleTime), so no request was sent and nothing was
                # intercepted (run3). Each case now also proves its injection
                # engaged. These are injected UI checks, never backend evidence.
                with harness.case(results, 'loading_state') as c:
                    injected = context.new_page()
                    held = []
                    injected.route(COMPANY_API, lambda route: held.append(route))
                    try:
                        injected.goto(link(base, manifest, 'typical'))
                        injected.wait_for_selector(f'{MAIN} [role=status]:has-text("Reading")')
                        screenshot(injected, 'loading-1440')
                        c.check(len(held) >= 1, f'no company request was held ({len(held)})')
                        # Release held requests BEFORE unroute; unroute first
                        # handles them ("Route is already handled!").
                        for route in held:
                            route.continue_()
                    finally:
                        injected.unroute(COMPANY_API)
                    wait_ready(injected)
                    c.check(injected.is_visible(DAY_GROUP), 'data did not replace the loading state')
                    injected.close()
                with harness.case(results, 'timeout_error') as c:
                    injected = context.new_page()
                    held = []
                    injected.route(COMPANY_API, lambda route: held.append(route))
                    try:
                        injected.goto(link(base, manifest, 'one_close'))
                        injected.wait_for_timeout(harness.BROWSER_TIMEOUT_MS + 1500)
                        c.check(len(held) >= 1, f'no company request was held ({len(held)})')
                        c.check('did not answer in time' in (injected.text_content(MAIN) or ''), 'no timeout notice')
                    finally:
                        for route in held:
                            route.abort()
                        injected.unroute(COMPANY_API)
                        injected.close()
                with harness.case(results, 'network_error_retry') as c:
                    injected = context.new_page()
                    aborted = []
                    injected.route(COMPANY_API, lambda route: (aborted.append(route.request.url), route.abort()))
                    try:
                        injected.goto(link(base, manifest, 'regime'))
                        injected.wait_for_selector(f'{MAIN} [role=alert]')
                        c.check(len(aborted) >= 1, f'no company request was aborted ({len(aborted)})')
                        c.check('Could not reach the analysis.' in (injected.text_content(MAIN) or ''),
                                'no network notice')
                    finally:
                        injected.unroute(COMPANY_API)
                    injected.click(f'{MAIN} button:has-text("Retry")')
                    wait_ready(injected)
                    c.check(injected.is_visible(DAY_GROUP), 'Retry did not recover')
                    injected.close()
                with harness.case(results, 'session_expiry') as c:
                    injected = context.new_page()
                    answers = []
                    injected.on('response', lambda response: answers.append(response.status)
                                if '/radar/api/analysis/company/' in response.url else None)
                    injected.goto(link(base, manifest, 'typical'))
                    wait_ready(injected)
                    context.clear_cookies()
                    answers.clear()
                    injected.fill('input[name=analysis_to]', manifest['window']['from'])
                    injected.fill('input[name=analysis_from]', manifest['window']['from'])
                    injected.click('button:has-text("Show these days")')
                    injected.wait_for_selector('text=Session expired.')
                    c.facts['company_answers_after_expiry'] = list(answers)
                    c.check(302 in answers, f'the expired request was not a login redirect: {answers}')
                    c.check(not injected.is_visible(DAY_GROUP), 'data still shown after expiry')
                    screenshot(injected, 'session-expired-1440')
            context.close()

        with harness.case(results, 'zoom_200') as c:
            context = browser.new_context(viewport={'width': 720, 'height': 500}, device_scale_factor=2)
            page = context.new_page()
            login(page, base, *admin)
            page.goto(link(base, manifest, 'typical'))
            wait_ready(page)
            c.check(no_overflow(page), 'document scrolls horizontally at 200% zoom')
            c.check(page.is_visible('main h1'), 'heading not visible at 200% zoom')
            buttons = page.locator(f'{DAY_GROUP} button')
            target = buttons.nth(2)
            target.scroll_into_view_if_needed()
            target.click()
            c.check(target.get_attribute('aria-pressed') == 'true', 'a day could not be selected at 200% zoom')
            small = small_targets(page)
            c.facts['small'] = small
            c.check(not small, f'{len(small)} control(s) under 44px at 200% zoom')
            window = manifest['window']
            field = page.locator('input[name=analysis_from]')
            field.scroll_into_view_if_needed()
            c.check(field.is_visible(), 'the range controls are not reachable at 200% zoom')
            page.fill('input[name=analysis_from]', window['to'])
            page.fill('input[name=analysis_to]', window['to'])
            page.click('button:has-text("Show these days")')
            page.wait_for_function('location.search.includes("analysis_from=' + window['to'] + '")')
            wait_ready(page)
            c.check(buttons.count() == 1, f'a one-day range rendered {buttons.count()} days at 200% zoom')
            screenshot(page, 'zoom-200')
            context.close()
        with harness.case(results, 'reduced_motion') as c:
            context = browser.new_context(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
            page = context.new_page()
            login(page, base, *admin)
            page.goto(link(base, manifest, 'typical'))
            wait_ready(page)
            c.check(page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches'), 'not emulated')
            duration = page.evaluate(f'getComputedStyle(document.querySelector({json.dumps(DAY_GROUP + " button")})).transitionDuration')
            c.check(duration in ('0s', ''), f'day buttons still transition: {duration}')
            context.close()
        with harness.case(results, 'non_admin_access') as c:
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            page = context.new_page()
            login(page, base, *plain)
            page.goto(link(base, manifest, 'typical'))
            wait_ready(page)
            c.check(page.is_visible(DAY_GROUP), 'an ordinary signed-in account could not read Analysis')
            c.facts['note'] = ('loopback host only; the production full-access host member gate '
                               '403s non-admins on the whole radar blueprint (app.py), unchanged; '
                               'asserted as exactly 403 in tests/test_radar_analysis_api.py')
            context.close()
        browser.close()

    with harness.case(results, 'source_build_identity') as c:
        current = harness.source_fingerprint(local_runtime.CANDIDATE)
        c.facts['digest'] = current['digest']
        for problem in harness.fingerprint_failures(record_fingerprint, current):
            c.check(False, problem)
        c.check(current['digest'] == record_fingerprint.get('digest'), 'source/build drift during the run')
    return results


def main():
    port, manifest, credentials, record_fingerprint = preflight(sys.argv)
    started = time.time()
    results = run(port, manifest, credentials, record_fingerprint)
    failures = harness.c16_failures(results)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'verify_preview.json').write_text(json.dumps(
        {'port': port, 'synthetic': True, 'seconds': round(time.time() - started, 1),
         'fingerprint': record_fingerprint['digest'], 'results': results, 'failures': failures},
        indent=2), encoding='utf-8')
    print('\n'.join(failures) if failures else 'all C15/C16 cases recorded without failures; now VIEW the PNGs')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
