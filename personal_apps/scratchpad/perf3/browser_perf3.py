"""Task 8 Step 4 (dispatched as Task 8b): both boards, end to end, in a real
browser.

python-playwright 1.61 with headless Chromium 149, against the real app served
by `serve_perf3.py` -- ONE web-model process with two request threads, the
concurrency of the deployed two sync workers; a MODEL, not gunicorn -- with
the real `run_radar_board_producer.py` running beside it, on
`personal_apps_radar_perf3_scale` through `scale_env`. The session cookie is
minted with the app's own signing serializer for a disposable `perf3_browser`
account, deleted afterwards; no password is typed anywhere. Every check runs
on BOTH `/radar/` (the old board) and `/radar/hub/` (the hub's Human chatter
page, the one that carries the window and size controls), at 1440x900:

  1  empty store     TRUNCATE both store tables and open a warm selection:
                     the pending copy, no rows, no "Nothing cleared", no
                     timestamp; then the board. Time to rows and time to
                     usable are measured in the page, apart.
  2  switching       six window/segment changes 200 ms apart, once from a
                     ready board and once from a pending one; every paint is
                     recorded; the final rows are held against `read_payload`
                     for the final selection.
  3  hidden          while pending (producer stopped): no poll during 10 s
                     hidden, one immediate poll on return.
  4  stale -> fresh  a warm row aged to 300 s by SQL: "Calculated 5m ago ·
                     refreshing", then the producer's refresh clears it.
  5  hard-expired    a warm row aged to 700 s: the pending state, never the
                     old board.
  6  delayed         producer stopped, a cold key, 31 s: the delayed copy and
                     its Retry; then the producer starts: rows, no reload.
  7  flag off        the server restarted with RADAR_BOARD_SHARED_RESULTS=off:
                     the old board past 120 s on its own clock says "not
                     refreshed" with a Retry and asks nothing; the hub re-reads
                     once, about 60 s after arrival.
  8  the star        the old board: star a ticker, change the window while
                     the mark is held in flight; the final board and the
                     address bar are the NEW selection's.
  m  phone           one pending and one ready screenshot per page, 390x844.

What the page does is read from inside it. An init script wraps `fetch` (every
request, and a digest of every board answer, on the page's own clock) and
records every distinct state the page paints -- rows, the waiting notice, the
age line, the context line, the controls -- so no timing depends on how often
this process looks.

Hidden is EMULATED. Headless Chromium reports `visible` for a background page
whatever is done to it: bring_to_front of another page, focus emulation off,
Page.setWebLifecycleState and a minimised window were probed in both
headless modes (Task 8b) and none changed `document.visibilityState`. So the
init script overrides the `visibilityState`/`hidden` getters and dispatches a
bubbling `visibilitychange`, which is what the old board's Poller, the hub's
useVisible and react-query's focusManager all read.

    cd personal_apps
    <python 3.12> scratchpad/perf3/browser_perf3.py [--checks 1,2,4,5,8,m,3,6,7]
"""
import argparse
import contextlib
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import traceback
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
APP_DIR = HERE.parents[1]
WORKTREE = APP_DIR.parent
SHOTS = WORKTREE / 'radar-design' / 'perf3-shots'


def _head():
    return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(WORKTREE),
                          capture_output=True, text=True,
                          check=True).stdout.strip()


# The HEAD this run starts from, pinned BEFORE scale_env is imported (it reads
# PERF3_REVISION then) and inherited by every child it starts: a commit during
# the run cannot move the namespace under the running processes.
os.environ.setdefault('PERF3_REVISION', _head())
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import sqlalchemy as sa  # noqa: E402

import env_check  # noqa: E402
import perf3_common as common  # noqa: E402
import scale_env  # noqa: E402

PORT_ON = 5090
PORT_OFF = 5091
VIEWPORT = {'width': 1440, 'height': 900}
PHONE = {'width': 390, 'height': 844}
USER = 'perf3_browser'
SOURCES = 'bluesky,fourchan,reddit'

# Filled by main() once the process is bound.
APP = ENGINE = NS = UID = None
RESULTS = []
# Things measured on the way that are not a check's verdict.
OBSERVATIONS = []


def sel(market, segment, window):
    """A selection as the client sends it: every parameter explicit."""
    return {'sources': SOURCES, 'window': str(window), 'segment': segment,
            'market': market}


def label(args):
    return f"{args['market']}/{args['segment'] or 'all'}/{args['window']}h"


US_ALL_24 = sel('us', '', 24)
US_ALL_12 = sel('us', '', 12)
US_DE_ALL_24 = sel('de', '', 24)

# Cold selections, one per use, so no check inherits another's queue.
COLD = {
    'hidden_old': sel('us', 'recent_ipo', 4),
    'hidden_hub': sel('us', 'recent_ipo', 1),
    'delayed_old': sel('de', 'large', 4),
    'delayed_hub': sel('de', 'large', 1),
    'phone_old': sel('us', 'mid', 4),
    'phone_hub': sel('us', 'micro', 4),
}

# (what moves, the old board's control, the hub's control, the selection
# after). The old board's segment control is a row of toggles (a union), the
# hub's a select, so each sequence only makes moves both have in one action.
SWITCH = {
    'ready': (US_ALL_12, [
        ('view', 'Large', ('Size', 'large'), sel('us', 'large', 12)),
        ('window', '24h', ('Window', '24'), sel('us', 'large', 24)),
        ('view', 'All', ('Size', 'all'), sel('us', '', 24)),
        ('window', '4h', ('Window', '4'), sel('us', '', 4)),
        ('view', 'Discover', ('Size', 'discover'), sel('us', 'discover', 4)),
        ('window', '24h', ('Window', '24'), sel('us', 'discover', 24)),
    ]),
    'pending': (sel('us', 'fund', 4), [
        ('window', '12h', ('Window', '12'), sel('us', 'fund', 12)),
        ('view', 'All', ('Size', 'all'), sel('us', '', 12)),
        ('window', '1h', ('Window', '1'), sel('us', '', 1)),
        ('view', 'Discover', ('Size', 'discover'), sel('us', 'discover', 1)),
        ('window', '24h', ('Window', '24'), sel('us', 'discover', 24)),
        ('view', 'All', ('Size', 'all'), sel('us', '', 24)),
    ]),
}

INIT_JS = r"""
(() => {
  if (window.__perf3) return;
  // --- hidden, emulated (headless Chromium never reports it) ---------------
  let hidden = false;
  Object.defineProperty(Document.prototype, 'visibilityState', {
    configurable: true, get() { return hidden ? 'hidden' : 'visible'; } });
  Object.defineProperty(Document.prototype, 'hidden', {
    configurable: true, get() { return hidden; } });
  const P = window.__perf3 = { requests: [], paints: [], firstRowsAt: null,
    firstWaitAt: null, usableAt: null, usableArmed: false, inflight: 0 };
  // Stamped on BOTH sides of the dispatch. A listener runs inside
  // dispatchEvent, and the old board's resume() calls fetch synchronously in
  // it, so a request sent in reply to the event starts before dispatchEvent
  // returns: a single stamp taken afterwards counted that reply as sent
  // while hidden (the first full run's check 3, old board).
  P.setHidden = (value) => {
    const before = performance.now();
    hidden = Boolean(value);
    document.dispatchEvent(new Event('visibilitychange', { bubbles: true }));
    return { before, after: performance.now() };
  };
  // --- every request, and what each board answer was ----------------------
  P.digest = (b) => ({ as_of: b.as_of, generated_at: b.generated_at,
    window: b.window_hours, market: b.market, segments: b.segments,
    sort: b.sort, pending: b.pending, busy: b.busy, stale: b.stale,
    failed: b.failed, shared: b.shared, age: b.age_seconds,
    fresh: b.fresh_seconds, retry: b.retry_after_ms,
    rows: b.rows ? b.rows.map((r) => r.ticker) : null,
    watch: (b.watch_rows || []).map((r) => r.ticker),
    watching: b.watching || [] });
  P.embedded = () => {
    const el = document.getElementById('radar-data')
      || document.getElementById('radar-hub-data');
    if (!el) return null;
    const raw = JSON.parse(el.textContent);
    return P.digest(raw.board || raw);
  };
  const realFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    const url = typeof input === 'string' ? input
      : (input && input.url) || String(input);
    const rec = { url, method: (init && init.method) || 'GET',
      t0: performance.now(), t1: null, status: null, error: null,
      board: null };
    P.requests.push(rec);
    P.inflight += 1;
    const settle = () => { P.inflight -= 1; setTimeout(P.record, 0); };
    return realFetch(input, init).then((response) => {
      rec.t1 = performance.now();
      rec.status = response.status;
      if (url.indexOf('/radar/api/board') !== -1 && response.ok) {
        response.clone().json().then(
          (b) => { rec.board = P.digest(b); }, () => {});
      }
      settle();
      return response;
    }, (error) => {
      rec.t1 = performance.now();
      rec.error = String((error && error.name) || error);
      settle();
      throw error;
    });
  };
  // --- what the page shows, every time it changes -------------------------
  const text = (sel) => {
    const e = document.querySelector(sel);
    return e ? e.textContent.replace(/\s+/g, ' ').trim() : null;
  };
  P.snap = () => {
    const hub = document.querySelector('.rh') !== null;
    const rows = Array.from(document.querySelectorAll(
      hub ? '[data-testid="rh-row-ticker"]' : '.rows a.row .tk'))
      .map((e) => e.textContent.trim());
    const age = document.querySelector(hub ? '.rh-age' : '.lhead .age');
    const s = { hub, rows,
      age: age ? age.textContent.replace(/\s+/g, ' ').trim() : null,
      ageClass: age ? age.className : null };
    if (hub) {
      s.wait = text('.rh-notice.rh-wait');
      s.context = text('.rh-datestamp');
      s.controls = Array.from(document.querySelectorAll('.rh-filters select'))
        .map((x) => x.value).join('|');
      s.empty = text('.rh-empty h2');
      s.loading = text('.rh-main .rh-panel[role="status"]');
      s.retry = document.querySelector('.rh-wait .rh-retry') !== null;
      s.ageRetry = document.querySelector('.rh-age button') !== null;
      s.busy = false;
      s.detail = null;
      s.banner = text('.rh-main > .rh-notice.amber');
    } else {
      s.wait = text('.rows p.none.pending') || text('.rows p.oops.inline');
      s.context = text('.rows p.tier.scored .what');
      const pressed = Array.from(document.querySelectorAll(
        '.controls .tabs.views button[aria-pressed="true"]'))
        .map((b) => (b.firstChild ? b.firstChild.textContent : '').trim());
      s.controls = `${text('.controls .summary .tok b') || '?'}|`
        + pressed.join('+');
      s.empty = text('.rows p.none:not(.pending)');
      s.loading = null;
      s.retry = document.querySelector('.rows p.none.pending button') !== null;
      s.ageRetry = document.querySelector('.lhead .age button') !== null;
      s.busy = document.querySelector('.rows[aria-busy="true"]') !== null;
      const detail = document.querySelector('main.detail');
      s.detail = detail ? detail.className : null;
      s.banner = text('.page > p.oops');
    }
    return s;
  };
  // Usable: rows, no waiting notice, the age line, nothing in flight, the
  // old board's panel settled for its ticker -- and then an idle main thread.
  const usable = (x) => x.rows.length > 0 && !x.wait && x.age !== null
    && /^Calculated/.test(x.age) && !x.busy && P.inflight === 0
    && (x.hub || (x.detail !== null && !/loading|empty/.test(x.detail)));
  let last = '';
  P.record = () => {
    const s = P.snap();
    const t = performance.now();
    const key = JSON.stringify([s.rows.join(','), s.wait,
      (s.age || '').replace(/[0-9]+/g, '#'),
      (s.context || '').replace(/ · Calculated.*$/, ''), s.controls, s.empty,
      s.loading, s.busy, s.detail, s.banner, s.retry, s.ageRetry]);
    if (key !== last) {
      last = key;
      P.paints.push({ t, rows: s.rows.join(','), n: s.rows.length,
        wait: s.wait, age: s.age, ageClass: s.ageClass, context: s.context,
        controls: s.controls, empty: s.empty, loading: s.loading,
        busy: s.busy, detail: s.detail, retry: s.retry,
        ageRetry: s.ageRetry, banner: s.banner });
    }
    if (s.rows.length && P.firstRowsAt === null) P.firstRowsAt = t;
    if (s.wait && P.firstWaitAt === null) P.firstWaitAt = t;
    if (P.usableAt === null && !P.usableArmed && usable(s)) {
      P.usableArmed = true;
      const idle = window.requestIdleCallback || ((f) => setTimeout(f, 0));
      idle(() => {
        P.usableArmed = false;
        if (P.usableAt === null && usable(P.snap())) {
          P.usableAt = performance.now();
        }
      }, { timeout: 2000 });
    }
  };
  const start = () => {
    P.record();
    new MutationObserver(P.record).observe(document.documentElement,
      { subtree: true, childList: true, characterData: true,
        attributes: true });
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
"""

ROWS_READY = ("() => { const s = window.__perf3.snap();"
              " return s.rows.length > 0 && !s.wait; }")
WAITING = '() => window.__perf3.snap().wait !== null'
USABLE = '() => window.__perf3.usableAt !== null'
POLLED = ("() => window.__perf3.requests.some((r) =>"
          " r.url.includes('/radar/api/board') && r.url.includes('poll=1'))")
FRESH_LINE = ("() => { const s = window.__perf3.snap(); return s.rows.length"
              " > 0 && /^Calculated \\d+s ago$/.test(s.age || ''); }")


# --- the store and the account ------------------------------------------------

def ready_idle(timeout=900):
    """Seconds until every warm board is fresh and nothing is queued."""
    with APP.app_context():
        return common.wait_ready_idle(ENGINE, NS, timeout=timeout)


def key(args):
    return common.key_of(args)[0]


def stored(args):
    """`read_payload` for the browser's account, as a worker would answer."""
    from extensions import db
    from features.radar import board_shared
    with APP.app_context():
        try:
            return board_shared.read_payload(ENGINE, args, scale_env.utcnow(),
                                              UID)
        finally:
            db.session.remove()


def make_cold(args, timeout=180):
    """Take a selection out of the store, waiting out a build in flight."""
    key_hash = key(args)
    deadline = time.monotonic() + timeout
    while True:
        common.delete_key(ENGINE, NS, key_hash)
        if common.key_row(ENGINE, NS, key_hash) is None:
            return key_hash
        if time.monotonic() > deadline:
            raise RuntimeError(f'{label(args)} stays in the store')
        time.sleep(1.0)


def age_row(args, seconds, timeout=120):
    """Move one published board's clock back so it is `seconds` old now.

    `as_of` and `built_at` move together, and only a row that is not being
    rebuilt and still holds the board this read found: a publish landing in
    between must not be overwritten with an invented age."""
    key_hash = key(args)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        now = scale_env.utcnow()
        with ENGINE.begin() as c:
            row = c.execute(sa.text(
                'SELECT as_of, built_at, queue_state FROM radar_board_results'
                ' WHERE namespace = :ns AND key_hash = :k'),
                {'ns': NS, 'k': key_hash}).mappings().first()
            if (row is not None and row['as_of'] is not None
                    and row['queue_state'] != 'building'):
                target = now - dt.timedelta(seconds=seconds)
                delta = target - row['as_of']
                built = (row['built_at'] + delta if row['built_at'] is not None
                         else None)
                moved = c.execute(sa.text(
                    'UPDATE radar_board_results SET as_of = :a, built_at = :b'
                    ' WHERE namespace = :ns AND key_hash = :k AND as_of = :old'
                    " AND queue_state <> 'building'"),
                    {'a': target, 'b': built, 'ns': NS, 'k': key_hash,
                     'old': row['as_of']}).rowcount
                if moved == 1:
                    return {'key': key_hash, 'was': row['as_of'],
                            'now': target, 'at': now}
        time.sleep(0.3)
    raise RuntimeError(f'could not age {label(args)}')


def clear_watches():
    with ENGINE.begin() as c:
        c.execute(sa.text('DELETE FROM radar_watch WHERE user_id = :u'),
                  {'u': UID})


# --- processes ------------------------------------------------------------------

class Stack:
    """The producer and the web-model server this run starts and stops."""

    def __init__(self, out):
        self.out = out
        self.producer = self.server = None
        self.starts = 0
        self.logs = []

    def start_producer(self):
        self.starts += 1
        began = time.perf_counter()
        self.producer = common.start_producer(self.out,
                                              name=f'producer{self.starts}')
        if self.producer.namespace != NS:
            raise SystemExit(f'producer namespace {self.producer.namespace}'
                             f' is not {NS}')
        self.logs.append(str(self.producer.log_path))
        return time.perf_counter() - began

    def stop_producer(self):
        """Stopped while idle, so no key is left `building` under a lease."""
        if self.producer is None:
            return
        ready_idle()
        self.producer.kill()
        self.producer = None

    def start_server(self, flag, port):
        self.server = common.start_web(self.out, port, name=f'web{port}-{flag}',
                                       flag=flag, threads=2)
        if self.server.namespace != NS:
            raise SystemExit(f'server namespace {self.server.namespace}'
                             f' is not {NS}')
        self.logs.append(str(self.server.log_path))

    def stop_server(self):
        if self.server is not None:
            self.server.kill()
            self.server = None

    def base(self):
        return f'http://127.0.0.1:{self.server.port}'

    def stop_all(self):
        common.stop_all([child for child in (self.server, self.producer)
                         if child is not None])
        self.server = self.producer = None


# --- the browser ------------------------------------------------------------------

def new_context(browser, cookie, viewport, phone=False):
    ctx = browser.new_context(viewport=viewport, is_mobile=phone,
                              has_touch=phone)
    ctx.add_cookies([{'name': 'session', 'value': cookie,
                      'domain': '127.0.0.1', 'path': '/'}])
    ctx.add_init_script(INIT_JS)
    return ctx


def url_for(kind, base, args):
    query = urllib.parse.urlencode(args)
    if kind == 'old':
        return f'{base}/radar/?{query}'
    return f'{base}/radar/hub/?{query}#chatter'


def query_of(url):
    parsed = urllib.parse.urlsplit(url)
    return dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))


def triple(args):
    return (args.get('market'), args.get('window'), args.get('segment'))


def board_requests(rec, since=None, until=None):
    return [r for r in rec['requests'] if '/radar/api/board' in r['url']
            and (since is None or r['t0'] > since)
            and (until is None or r['t0'] <= until)]


def is_poll(request):
    return 'poll=1' in request['url']


class Tab:
    """One page, and what its init script recorded."""

    def __init__(self, ctx, url, kind, timeout_s=90):
        self.kind = kind
        self.errors = []
        self.page = ctx.new_page()
        self.page.on('pageerror',
                     lambda error: self.errors.append(f'pageerror {error}'))
        self.page.on('console', self._console)
        self.opened = time.perf_counter()
        self.page.goto(url, wait_until='domcontentloaded',
                       timeout=timeout_s * 1000)
        self.page.wait_for_function(
            "() => document.querySelector('.lhead, .rh-main') !== null",
            timeout=timeout_s * 1000)

    def _console(self, message):
        if message.type in ('error', 'warning'):
            self.errors.append(f'console.{message.type} {message.text}')

    def wait(self, predicate, timeout_s, arg=None):
        self.page.wait_for_function(predicate, arg=arg,
                                    timeout=timeout_s * 1000, polling=100)

    def snap(self):
        return self.page.evaluate('window.__perf3.snap()')

    def now(self):
        return self.page.evaluate('performance.now()')

    def embedded(self):
        return self.page.evaluate('window.__perf3.embedded()')

    def text(self):
        return self.page.evaluate('document.body.innerText')

    def record(self):
        return self.page.evaluate("""() => { const P = window.__perf3;
          const nav = performance.getEntriesByType('navigation')[0];
          return { paints: P.paints, requests: P.requests,
            firstRowsAt: P.firstRowsAt, firstWaitAt: P.firstWaitAt,
            usableAt: P.usableAt, inflight: P.inflight,
            now: performance.now(),
            responseEnd: nav ? nav.responseEnd : null }; }""")

    def quiet(self, quiet_ms=2000, timeout_s=60):
        """Wait until nothing has been in flight for `quiet_ms`."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            state = self.page.evaluate("""() => { const P = window.__perf3;
              const ends = P.requests.map((r) => r.t1 === null ? Infinity : r.t1);
              return { inflight: P.inflight, now: performance.now(),
                       last: ends.length ? Math.max(...ends) : 0 }; }""")
            if state['inflight'] == 0 and state['now'] - state['last'] >= quiet_ms:
                return
            self.page.wait_for_timeout(200)
        raise TimeoutError(f'{self.kind}: requests never went quiet')

    def close(self):
        with contextlib.suppress(Exception):
            self.page.close()


def click_old(page, what, text):
    if what == 'window':
        page.locator('#radar-filters [aria-label="Window"] button').filter(
            has_text=re.compile(rf'^{re.escape(text)}$')).click()
    else:
        page.locator('.controls .tabs.views button').filter(
            has_text=re.compile(rf'^{re.escape(text)}')).click()


def select_hub(page, field, value):
    page.locator('.rh-filters label.rh-field').filter(
        has=page.locator('span', has_text=re.compile(rf'^{field}$'))
    ).locator('select').select_option(value)


# --- recording results ------------------------------------------------------------

class Check:
    def __init__(self, number, page, title):
        self.r = {'check': str(number), 'page': page, 'title': title,
                  'failures': [], 'notes': [], 'numbers': {}, 'shots': []}
        print(f'\n--- check {number} [{page}] {title}', flush=True)

    def expect(self, ok, message):
        if not ok:
            self.r['failures'].append(message)
            print(f'  FAIL {message}', flush=True)
        return ok

    def note(self, message):
        self.r['notes'].append(message)
        print(f'  note {message}', flush=True)

    def number(self, name, value):
        self.r['numbers'][name] = value
        print(f'  {name}: {value}', flush=True)

    def shot(self, tab, name, what):
        SHOTS.mkdir(parents=True, exist_ok=True)
        tab.page.screenshot(path=str(SHOTS / name))
        self.r['shots'].append({'file': name, 'what': what})
        print(f'  shot {name}', flush=True)

    def finish(self, tabs=()):
        for tab in tabs:
            if tab is not None and tab.errors:
                self.r.setdefault('page_errors', []).extend(tab.errors[:20])
        self.r['verdict'] = 'FAIL' if self.r['failures'] else 'PASS'
        RESULTS.append(self.r)
        print(f"  => {self.r['verdict']}", flush=True)


@contextlib.contextmanager
def checking(number, page, title):
    c = Check(number, page, title)
    c.tabs = []
    try:
        yield c
    except Exception as problem:                          # noqa: BLE001
        c.r['failures'].append(f'harness exception: {problem!r}'[:600])
        c.r['traceback'] = traceback.format_exc()
        print(traceback.format_exc(), flush=True)
    finally:
        c.finish(c.tabs)
        for tab in c.tabs:
            tab.close()


def seconds(ms):
    return None if ms is None else round(ms / 1000.0, 2)


def first_paint(rec, predicate, since=None):
    for paint in rec['paints']:
        if (since is None or paint['t'] > since) and predicate(paint):
            return paint
    return None


# --- 1: the empty store ----------------------------------------------------------

def check_empty(stack, ctx, kind):
    args = US_ALL_24
    key_hash = key(args)
    with checking(1, kind, f'empty store -> {label(args)}') as c:
        ready_idle()
        common.truncate_store(ENGINE)
        truncated = scale_env.utcnow()
        tab = Tab(ctx, url_for(kind, stack.base(), args), kind)
        c.tabs.append(tab)
        tab.wait(WAITING, 60)
        s = tab.snap()
        c.expect(s['rows'] == [], f"{len(s['rows'])} rows on screen while pending")
        c.expect((s['wait'] or '').startswith('Calculating this board'),
                 f"the pending copy reads {s['wait']!r}")
        c.expect(s['empty'] is None, f"an empty-board message: {s['empty']!r}")
        c.expect(s['age'] is None, f"a timestamp while pending: {s['age']!r}")
        body = tab.text()
        c.expect('Nothing cleared' not in body and 'No company cleared' not in body,
                 'an empty-board sentence in the page text while pending')
        c.expect('Calculated' not in body, 'a "Calculated" stamp while pending')
        embedded = tab.embedded()
        c.expect(embedded['pending'] and embedded['rows'] is None,
                 f'the embedded answer was not a pending shell: {embedded}')
        c.shot(tab, f'8b-1-{kind}-empty-pending.png',
               'empty store: the pending copy, no rows, no stamp')
        tab.wait(ROWS_READY, 180)
        tab.wait(USABLE, 60)
        rec = tab.record()
        s = tab.snap()
        c.number('document ms', round(rec['responseEnd'] or 0))
        c.number('pending copy at s', seconds(rec['firstWaitAt']))
        c.number('time to rows s', seconds(rec['firstRowsAt']))
        c.number('time to usable s', seconds(rec['usableAt']))
        late = first_paint(rec, lambda p: 'Still calculating' in (p['wait'] or ''))
        c.number('delayed copy at s', seconds(late['t']) if late else None)
        requests = board_requests(rec)
        c.number('board requests while waiting', len(requests))
        c.expect(all(is_poll(r) for r in requests),
                 'a board request while waiting that was not poll=1')
        c.expect((s['age'] or '').startswith('Calculated'),
                 f"the age line once the board arrived: {s['age']!r}")
        c.number('age line on arrival', (first_paint(
            rec, lambda p: p['n'] > 0) or {}).get('age'))
        c.shot(tab, f'8b-1-{kind}-empty-ready.png',
               'empty store: the board arrived, with its age line')
        answer = stored(args)
        c.expect(answer['rows'] is not None and set(s['rows']) == {
            row['ticker'] for row in answer['rows']},
            'the rows on screen are not the stored board')
        ready_idle()
        warm = sorted((row for row in common.ns_rows(ENGINE, NS) if row['warm']),
                      key=lambda row: row['as_of'])
        mine = common.key_row(ENGINE, NS, key_hash)
        position = next((i for i, row in enumerate(warm, 1)
                         if row['key_hash'] == key_hash), None)
        c.number('rebuild position of 8', position)
        if mine and mine['built_at']:
            c.number('published s after TRUNCATE', round(
                (mine['built_at'] - truncated).total_seconds(), 1))
            c.number('build ms', mine['build_ms'])


# --- 2: rapid switching ------------------------------------------------------------

def check_switching(stack, ctx, kind, variant):
    start, steps = SWITCH[variant]
    final = steps[-1][3]
    with checking(2, kind, f'six changes 200 ms apart from a {variant} board'
                  f' ({label(start)} -> {label(final)})') as c:
        if variant == 'pending':
            make_cold(start)
        else:
            ready_idle()
        tab = Tab(ctx, url_for(kind, stack.base(), start), kind)
        c.tabs.append(tab)
        if variant == 'pending':
            tab.wait(WAITING, 30)
            tab.wait(POLLED, 15)
        else:
            tab.wait(ROWS_READY, 30)
            tab.wait(USABLE, 30)
        if kind == 'old':
            tab.page.locator('.controls .summary button').click()
            tab.page.wait_for_selector('#radar-filters')
        tab.page.wait_for_timeout(400)
        before = tab.snap()
        began = time.perf_counter()
        samples, moments = [], []
        for index, (what, old_text, (field, value), after) in enumerate(steps):
            due = began + 0.2 * index
            while time.perf_counter() < due:
                tab.page.wait_for_timeout(
                    max(1, int((due - time.perf_counter()) * 1000)))
            moments.append(tab.now())
            if kind == 'old':
                click_old(tab.page, what, old_text)
            else:
                select_hub(tab.page, field, value)
            look = due + 0.1
            while time.perf_counter() < look:
                tab.page.wait_for_timeout(
                    max(1, int((look - time.perf_counter()) * 1000)))
            s = tab.snap()
            samples.append({'step': index + 1, 'selection': label(after),
                            'at_ms': round(moments[-1]), 'rows': len(s['rows']),
                            'first_rows': s['rows'][:3], 'wait': s['wait'],
                            'context': s['context'], 'controls': s['controls'],
                            'busy': s['busy']})
        c.number('change intervals ms', [round(b - a) for a, b in
                                         zip(moments, moments[1:])])
        c.r['samples'] = samples
        want = triple(final)
        # Settled: the latest answer WITH ROWS for the final selection is the
        # one on screen and nothing is in flight. (The old board keeps its
        # previous board up until the debounced request answers, so "rows and
        # nothing in flight" alone would stop on the start board.)
        deadline = time.monotonic() + 150
        while True:
            rec = tab.record()
            s = tab.snap()
            done = [r for r in rec['requests'] if r['board'] is not None
                    and r['board']['rows'] is not None
                    and triple(query_of(r['url'])) == want]
            if (done and rec['inflight'] == 0 and not s['wait']
                    and same_set(s['rows'], max(
                        done, key=lambda r: r['t1'])['board']['rows'])):
                break
            if time.monotonic() > deadline:
                raise TimeoutError("the final selection's board never settled")
            tab.page.wait_for_timeout(200)
        tab.page.wait_for_timeout(6000)       # time for a late answer to land
        rec = tab.record()
        s = tab.snap()
        first = moments[0]
        last = moments[-1]
        requests = board_requests(rec)
        after_first = board_requests(rec, since=first)
        c.number('board requests from the first change on', len(after_first))
        c.number('...of them poll=1', sum(map(is_poll, after_first)))
        sent_for = [(label_of_url(r['url']), round(r['t0'] - first), is_poll(r))
                    for r in after_first]
        c.r['requests_after_first_change'] = sent_for
        stray = [r for r in board_requests(rec, since=last)
                 if triple(query_of(r['url'])) != want]
        c.expect(not stray, 'a board request after the last change for another'
                 f' selection: {[label_of_url(r["url"]) for r in stray]}')
        if kind == 'old':
            # Nothing at all inside the burst: the change stops the wait, and
            # the debounce holds the one request until the controls settle.
            during = board_requests(rec, since=first + 30, until=last + 200)
            c.expect(not during, 'the old board sent a board request inside'
                     f' the burst: {[label_of_url(r["url"]) for r in during]}')
        finals = [r for r in requests if r['board'] is not None
                  and r['board']['rows'] is not None
                  and triple(query_of(r['url'])) == want]
        c.expect(bool(finals), 'no answer with rows for the final selection')
        answer = max(finals, key=lambda r: r['t1']) if finals else None
        if answer:
            c.expect(same_set(s['rows'], answer['board']['rows']),
                     'the rows on screen are not the final answer\'s rows')
            c.number('same order as the final answer',
                     s['rows'] == answer['board']['rows'])
            c.expect(str(answer['board']['window']) == final['window'],
                     f"the final answer echoes window {answer['board']['window']}")
            c.number('start and final boards distinguishable by rows',
                     not same_set(before['rows'], answer['board']['rows']))
        window_seen = context_window(kind, s)
        c.number('window in the rendered context line', window_seen)
        if window_seen is not None:
            c.expect(window_seen == int(final['window']),
                     f'the context line names {window_seen}h')
        else:
            c.note('no rendered window on the old board (no scored caption)')
        board = stored(final)
        on_store = [row['ticker'] for row in (board['rows'] or [])]
        c.number('rows on screen / in read_payload', f'{len(s["rows"])} /'
                 f' {len(on_store)}')
        if answer and board['as_of'] == answer['board']['as_of']:
            c.expect(set(s['rows']) == set(on_store),
                     'the rows on screen are not read_payload\'s for the final'
                     ' selection')
            c.number('same order as read_payload', s['rows'] == on_store)
        else:
            c.note(f"read_payload's board (as_of {board['as_of']}) is not the"
                   ' one on screen; compared with the answer the page drew')
        violations = overwrite_violations(kind, rec, first, before, answer)
        c.r['violations'] = violations
        c.expect(not violations, f'{len(violations)} paint(s) not of their'
                 f' selection: {violations[:3]}')
        c.number('paints after the first change', len(
            [p for p in rec['paints'] if p['t'] > first]))
        if kind == 'old':
            painted = first_paint(rec, lambda p: answer is not None
                                  and same_set(p['rows'].split(','),
                                               answer['board']['rows']),
                                  since=first)
            c.number('final rows painted ms after the last change',
                     round(painted['t'] - last) if painted else None)
        c.shot(tab, f'8b-2-{kind}-switch-{variant}-final.png',
               f'after six changes from a {variant} board: {label(final)}')


def label_of_url(url):
    q = query_of(url)
    return f"{q.get('market')}/{q.get('segment') or 'all'}/{q.get('window')}h"


def same_set(one, other):
    """Two ticker lists with the same members. The old board draws the
    server's order split into its two tiers, so membership is what says whose
    board it is; order is reported beside it."""
    one = [t for t in one if t]
    other = [t for t in (other or []) if t]
    return len(one) == len(other) and set(one) == set(other)


def context_window(kind, snap):
    if kind == 'hub':
        match = re.search(r'last (\d+) hours?', snap['context'] or '')
    else:
        match = re.search(r'the (\d+)h price move', snap['context'] or '')
    return int(match.group(1)) if match else None


def overwrite_violations(kind, rec, first, before, answer):
    """Paints after the first change whose rows are not their selection's.

    The hub draws only the current key's answer, so every paint with rows must
    be the answer to the selection its own controls show. The old board keeps
    the board it has while the next one loads (the list is marked busy once the
    request is out), so after the first change it may show only that board or
    the final one -- and once the final one is up, nothing else."""
    answers = [r for r in rec['requests'] if r['board'] is not None
               and r['board']['rows'] is not None]
    out = []
    final_rows = answer['board']['rows'] if answer else None
    seen_final = False
    for paint in rec['paints']:
        if paint['t'] <= first or paint['n'] == 0:
            continue
        rows = paint['rows'].split(',')
        is_final = final_rows is not None and same_set(rows, final_rows)
        if kind == 'hub':
            market, window, size, _ = (paint['controls'] or '|||').split('|')
            segment = '' if size == 'all' else size
            owners = [triple(query_of(r['url'])) for r in answers
                      if same_set(rows, r['board']['rows'])]
            context = re.search(r'last (\d+) hours?', paint['context'] or '')
            if (market, window, segment) not in owners or (
                    context and context.group(1) != window):
                out.append({'t': round(paint['t']), 'controls': paint['controls'],
                            'context': paint['context'],
                            'owners': [f'{m}/{g or "all"}/{w}h'
                                       for m, w, g in owners]})
        else:
            allowed = same_set(rows, before['rows']) or is_final
            if not allowed or (seen_final and not is_final):
                out.append({'t': round(paint['t']),
                            'controls': paint['controls'],
                            'first_rows': rows[:3]})
        if is_final:
            seen_final = True
    return out


def discover_key_note():
    """The old board's Discover tab and the hub's Discover size both ask for
    `segment=discover`; the producer keeps DEFAULT_SEGMENT warm. Segments are
    part of the key verbatim (Task 1), so these are two keys. Recorded, with
    whether the two hold the same rows, right after check 2 built the tab's."""
    from features.radar.config import DEFAULT_SEGMENT
    tab_args = sel('us', 'discover', 24)
    default_args = sel('us', DEFAULT_SEGMENT, 24)
    warm = {common.key_of(a)[0] for a in common.warm_args()}
    note = {'what': 'the Discover tab key against the warm default key',
            'tab_segment': 'discover', 'default_segment': DEFAULT_SEGMENT,
            'tab_key': key(tab_args)[:12], 'default_key': key(default_args)[:12],
            'tab_key_warm': key(tab_args) in warm,
            'default_key_warm': key(default_args) in warm}
    one, two = stored(tab_args), stored(default_args)
    note['tab_board'] = 'pending' if one['rows'] is None else 'ready'
    if one['rows'] is not None and two['rows'] is not None:
        note['same_rows_same_order'] = ([r['ticker'] for r in one['rows']]
                                        == [r['ticker'] for r in two['rows']])
    note['echoed_segments'] = {'tab': one['segments'],
                               'default': two['segments']}
    OBSERVATIONS.append(note)
    print(f'\nobservation: {note}', flush=True)


# --- 3: hidden while pending --------------------------------------------------------

def check_hidden(stack, ctx, kind, args):
    with checking(3, kind, f'hidden while pending ({label(args)})') as c:
        make_cold(args)
        tab = Tab(ctx, url_for(kind, stack.base(), args), kind)
        c.tabs.append(tab)
        tab.wait(WAITING, 30)
        tab.wait(POLLED, 15)
        tab.page.wait_for_timeout(400)
        hide = tab.page.evaluate('window.__perf3.setHidden(true)')
        tab.page.wait_for_timeout(10_000)
        show = tab.page.evaluate('window.__perf3.setHidden(false)')
        tab.page.wait_for_timeout(2500)
        rec = tab.record()
        hid, shown = hide['before'], show['before']
        # Classified against the stamps taken BEFORE each dispatch: a request
        # a visibility listener sends starts inside the dispatch it answers.
        requests = board_requests(rec)
        before = [r for r in requests if r['t0'] < hid]
        during = [r for r in requests if hid <= r['t0'] < shown]
        after = [r for r in requests if shown <= r['t0'] <= shown + 1500]
        c.r['timeline'] = [{'t0_ms_after_hide': round(r['t0'] - hid, 1),
                            'url': label_of_url(r['url']), 'poll': is_poll(r),
                            'answered_ms': (round(r['t1'] - r['t0'])
                                            if r['t1'] else None)}
                           for r in requests]
        c.number('hidden for s', seconds(shown - hid))
        c.number('polls before hiding', sum(map(is_poll, before)))
        c.number('poll in flight at the hide', any(
            r['t1'] is None or r['t1'] > hid for r in before))
        c.number('board requests during 10 s hidden', len(during))
        c.number('...of them poll=1', sum(map(is_poll, during)))
        c.expect(not during, f'{len(during)} board request(s) while hidden')
        c.number('board requests within 1.5 s of visible', len(after))
        c.expect(len(after) == 1, f'{len(after)} request(s) on return, not one')
        if after:
            c.number('first request after visible ms',
                     round(after[0]['t0'] - shown, 1))
            c.number('sent inside the visibilitychange handler',
                     after[0]['t0'] <= show['after'])
            c.expect(is_poll(after[0]), 'the request on return was not poll=1')
        s = tab.snap()
        c.expect(not s['rows'] and (s['wait'] or '').startswith('Calculating'),
                 f"not still pending at the end: {s['wait']!r}")
        c.shot(tab, f'8b-3-{kind}-hidden-returned.png',
               'hidden 10 s while pending, then visible: still pending')
    make_cold(args)            # out of the queue: check 6 must not wait on it


# --- 4 and 5: an aged row -------------------------------------------------------------

def load_aged(ctx, stack, kind, args, age_s, expected):
    """Age the row, load the page, return the tab and how many tries it took.

    The producer rebuilds a due key within about five seconds of it becoming
    due; a page that reads the row after that sees the NEW board. That is the
    harness losing a race, not the page misbehaving, so it is tried again once
    and said."""
    for attempt in (1, 2):
        ready_idle()
        aged = age_row(args, age_s)
        tab = Tab(ctx, url_for(kind, stack.base(), args), kind)
        tab.wait("() => { const s = window.__perf3.snap();"
                 " return s.wait !== null || s.rows.length > 0; }", 30)
        if expected(tab.snap()):
            return tab, attempt, aged
        tab.close()
    return tab, attempt, aged


def check_stale(stack, ctx, kind, args):
    with checking(4, kind, f'stale to fresh ({label(args)})') as c:
        tab, attempt, aged = load_aged(
            ctx, stack, kind, args, 300,
            lambda s: 'refreshing' in (s['age'] or ''))
        c.tabs.append(tab)
        if attempt > 1:
            c.note('the first load found the refresh already published; aged'
                   ' again')
        tab.wait(ROWS_READY, 30)
        s = tab.snap()
        embedded = tab.embedded()
        c.number('embedded age s', round(embedded['age'], 1)
                 if embedded['age'] is not None else None)
        c.number('age line at load', s['age'])
        c.expect(re.fullmatch(r'Calculated 5m ago · refreshing', s['age'] or ''),
                 f"the age line at load reads {s['age']!r}")
        c.expect('stale' in (s['ageClass'] or ''), 'the age line is not marked'
                 ' stale')
        c.expect(embedded['stale'] is True and embedded['rows'] is not None,
                 'the embedded answer was not a stale board')
        c.shot(tab, f'8b-4-{kind}-stale-refreshing.png',
               'a warm board aged to 300 s: "Calculated 5m ago · refreshing"')
        tab.wait(FRESH_LINE, 120)
        rec = tab.record()
        cleared = first_paint(rec, lambda p: re.fullmatch(
            r'Calculated \d+s ago', p['age'] or '') is not None)
        c.number('marker cleared at s', seconds(cleared['t']) if cleared else None)
        c.number('age line after', tab.snap()['age'])
        polls = board_requests(rec)
        c.number('board requests until then', len(polls))
        c.expect(all(is_poll(r) for r in polls), 'a non-poll request while the'
                 ' refresh was awaited')
        fresh = [r['board'] for r in polls if r['board'] and not r['board']['stale']]
        if fresh:
            c.number('refreshed board as_of', fresh[0]['as_of'])
        c.expect('stale' not in (tab.snap()['ageClass'] or ''),
                 'the age line still marked stale')
        c.shot(tab, f'8b-4-{kind}-stale-cleared.png',
               'the producer\'s refresh landed: the marker cleared, no reload')


def check_expired(stack, ctx, kind, args):
    with checking(5, kind, f'hard-expired ({label(args)})') as c:
        tab, attempt, aged = load_aged(
            ctx, stack, kind, args, 700, lambda s: s['wait'] is not None)
        c.tabs.append(tab)
        if attempt > 1:
            c.note('the first load found the rebuild already published; aged'
                   ' again')
        s = tab.snap()
        embedded = tab.embedded()
        c.expect(embedded['pending'] and embedded['rows'] is None,
                 f'the embedded answer: {embedded}')
        c.expect(not s['rows'], f"{len(s['rows'])} rows shown for a board 700 s"
                 ' old')
        c.expect((s['wait'] or '').startswith('Calculating this board'),
                 f"the waiting copy reads {s['wait']!r}")
        c.expect(s['age'] is None, f"a timestamp shown: {s['age']!r}")
        c.shot(tab, f'8b-5-{kind}-expired-pending.png',
               'a warm board aged to 700 s: the pending state, not the board')
        tab.wait(ROWS_READY, 120)
        rec = tab.record()
        c.number('time to rows s', seconds(rec['firstRowsAt']))
        c.number('age line then', tab.snap()['age'])
        c.shot(tab, f'8b-5-{kind}-expired-rebuilt.png',
               'the rebuilt board arrived by poll')


# --- 6: delayed, then the producer ----------------------------------------------------

def check_delayed(stack, ctx):
    pages = (('old', COLD['delayed_old']), ('hub', COLD['delayed_hub']))
    checks, tabs = {}, {}
    try:
        for kind, args in pages:
            checks[kind] = Check(6, kind, f'delayed, producer stopped, then'
                                 f' started ({label(args)})')
            make_cold(args)
            tabs[kind] = Tab(ctx, url_for(kind, stack.base(), args), kind)
            tabs[kind].wait(WAITING, 30)
        for kind, tab in tabs.items():
            rec = tab.record()
            left = rec['firstWaitAt'] + 31_000 - rec['now']
            if left > 0:
                tab.page.wait_for_timeout(left)
        for kind, tab in tabs.items():
            c = checks[kind]
            s = tab.snap()
            rec = tab.record()
            c.number('waited s', seconds(rec['now'] - rec['firstWaitAt']))
            c.number('waiting copy', s['wait'])
            c.expect((s['wait'] or '').startswith('Still calculating'),
                     f"not the delayed copy at 31 s: {s['wait']!r}")
            c.expect('built from scratch' in (s['wait'] or ''),
                     'the delayed copy does not say why')
            c.expect('Change the window or the feeds' in (s['wait'] or ''),
                     'the delayed copy offers no way out')
            c.expect(s['retry'], 'no Retry beside the delayed copy')
            c.expect(not s['rows'], 'rows while delayed')
            c.shot(tab, f'8b-6-{kind}-delayed.png',
                   'producer stopped, 31 s: the delayed copy and its Retry')
            tab.page.evaluate('window.__perf3NoReload = performance.timeOrigin')
            tab.spawned = tab.now()
        startup = stack.start_producer()
        for kind, tab in tabs.items():
            tab.started = tab.now()
        for kind, tab in tabs.items():
            c = checks[kind]
            c.number('producer start to namespace line s', round(startup, 1))
            tab.wait(ROWS_READY, 300)
            rec = tab.record()
            # The wait's own cadence once it is long: every poll from the 30 s
            # mark until the board was on screen (the schedule's SLOW_MS, 5 s
            # plus up to a fifth of jitter, or the server's floor if higher).
            polls = [r['t0'] for r in board_requests(rec)
                     if rec['firstWaitAt'] + 30_000 <= r['t0']
                     <= rec['firstRowsAt']]
            c.number('poll gaps from 30 s until the board ms',
                     [round(b - a) for a, b in zip(polls, polls[1:])])
            c.number('rows s after the producer was spawned',
                     seconds(rec['firstRowsAt'] - tab.spawned))
            c.number('rows s after it logged its namespace',
                     seconds(rec['firstRowsAt'] - tab.started))
            same = tab.page.evaluate(
                'window.__perf3NoReload === performance.timeOrigin')
            c.expect(same, 'the page was reloaded')
            s = tab.snap()
            c.expect((s['age'] or '').startswith('Calculated'),
                     f"no age line after recovery: {s['age']!r}")
            c.shot(tab, f'8b-6-{kind}-recovered.png',
                   'the producer started: the board arrived with no reload')
    except Exception as problem:                          # noqa: BLE001
        for c in checks.values():
            c.r['failures'].append(f'harness exception: {problem!r}'[:600])
        print(traceback.format_exc(), flush=True)
    finally:
        for kind, c in checks.items():
            c.finish([tabs.get(kind)])
        for tab in tabs.values():
            tab.close()
        if stack.producer is None:
            stack.start_producer()


# --- 7: the flag off -----------------------------------------------------------------

def check_flag_off(stack, ctx):
    old_c = Check(7, 'old', f'flag off: past 120 s on the page clock'
                  f' ({label(US_ALL_24)})')
    hub_c = Check(7, 'hub', f'flag off: one re-read about 60 s after arrival'
                  f' ({label(US_ALL_12)})')
    hub = old = None
    try:
        stack.stop_producer()
        stack.stop_server()
        stack.start_server('off', PORT_OFF)
        base = stack.base()
        hub = Tab(ctx, url_for('hub', base, US_ALL_12), 'hub', timeout_s=300)
        hub.wait(ROWS_READY, 300)
        hub_emb = hub.embedded()
        hub_c.number('embedded shared / age s', f"{hub_emb['shared']} /"
                     f" {round(hub_emb['age'] or 0, 1)}")
        hub_c.expect(hub_emb['shared'] is False, 'the hub board says shared')
        hub_rec = hub.record()
        arrived = hub_rec['firstRowsAt']
        old = Tab(ctx, url_for('old', base, US_ALL_24), 'old', timeout_s=300)
        old.wait(ROWS_READY, 300)
        old_emb = old.embedded()
        age0 = old_emb['age'] or 0.0
        old_c.number('embedded shared / age s', f"{old_emb['shared']} /"
                     f' {round(age0, 1)}')
        old_c.expect(old_emb['shared'] is False, 'the old board says shared')
        old_arrived = old.record()['firstRowsAt']
        old.wait("() => /not refreshed/.test(window.__perf3.snap().age || '')",
                 125 - age0 + 60)
        rec = old.record()
        crossed = first_paint(rec, lambda p: 'not refreshed' in (p['age'] or ''))
        old_c.number('"not refreshed" at page-clock age s', round(
            (crossed['t'] - old_arrived) / 1000 + age0, 1))
        s = old.snap()
        old_c.number('age line', s['age'])
        # The Retry is a button inside the line, so its word follows with no
        # space in the text content.
        old_c.expect(re.fullmatch(r'Calculated 2m ago · not refreshed\s*Retry',
                                  s['age'] or '') is not None,
                     f"the age line reads {s['age']!r}")
        old_c.expect(s['ageRetry'], 'no Retry in the age line')
        old_c.expect('stale' in (s['ageClass'] or ''), 'not marked stale')
        old_c.shot(old, '8b-7-old-flagoff-not-refreshed.png',
                   'flag off, past 120 s on the page clock: "not refreshed"'
                   ' with Retry')
        old.page.wait_for_timeout(20_000)
        rec = old.record()
        asked = board_requests(rec)
        old_c.number('board requests from load to +20 s past the bound',
                     len(asked))
        old_c.expect(not asked, f'{len(asked)} automatic board request(s)')
        old_c.number('observed s after arrival', seconds(rec['now'] - old_arrived))
        hub_rec = hub.record()
        reads = board_requests(hub_rec)
        gaps = [seconds(r['t0'] - arrived) for r in reads]
        hub_c.number('board reads at s after arrival', gaps)
        hub_c.expect(bool(reads), 'the hub never re-read its board')
        if reads:
            hub_c.expect(55 <= gaps[0] <= 70, f'the first re-read at {gaps[0]} s')
            hub_c.expect(len([g for g in gaps if g <= gaps[0] + 2]) == 1,
                         'more than one read around the minute')
            hub_c.expect(not is_poll(reads[0]), 'the minute\'s read was poll=1')
            hub_c.number('first read answered s later',
                         seconds(reads[0]['t1'] - reads[0]['t0'])
                         if reads[0]['t1'] else None)
            fresh = reads[0]['board']
            if fresh:
                hub_c.number('its answer: shared / age s',
                             f"{fresh['shared']} / {round(fresh['age'] or 0, 1)}")
        hub_c.number('hub age line now', hub.snap()['age'])
        hub_c.shot(hub, '8b-7-hub-flagoff-reread.png',
                   'flag off: the hub after its minute\'s re-read')
    except Exception as problem:                          # noqa: BLE001
        for c in (old_c, hub_c):
            c.r['failures'].append(f'harness exception: {problem!r}'[:600])
        print(traceback.format_exc(), flush=True)
    finally:
        old_c.finish([old])
        hub_c.finish([hub])
        for tab in (old, hub):
            if tab is not None:
                tab.close()
        stack.stop_server()


# --- 8: the star ------------------------------------------------------------------------

def check_star(stack, ctx, variant, start, moved, row_index):
    """Star a ticker and move a filter while the mark is held in flight.

    The PUT is paused by route interception (never a sleep in the handler,
    which would block this process's event loop) and released once the new
    selection's board has been asked for -- or, in variant B, inside the
    250 ms the controls take to settle."""
    title = {'A': 'the mark lands after the new board is up',
             'B': 'the mark lands inside the controls\' debounce'}[variant]
    with checking(8, 'old', f'star {variant}: {title} ({label(start)} ->'
                  f' {label(moved)})') as c:
        ready_idle()
        tab = Tab(ctx, url_for('old', stack.base(), start), 'old')
        c.tabs.append(tab)
        tab.wait(ROWS_READY, 30)
        tab.wait(USABLE, 30)
        tab.page.locator('.controls .summary button').click()
        tab.page.wait_for_selector('#radar-filters')
        held = []
        tab.page.route('**/radar/api/watch/**', lambda route: held.append(route))
        rows = tab.snap()['rows']
        ticker = rows[row_index]
        c.number('starred', ticker)
        tab.page.get_by_role('button', name=f'Watch {ticker}', exact=True).click()
        starred = tab.now()
        deadline = time.monotonic() + 5
        while not held and time.monotonic() < deadline:
            tab.page.wait_for_timeout(25)
        c.expect(bool(held), 'the mark never went out')
        c.expect(tab.page.get_by_role('button', name=f'Stop watching {ticker}',
                                      exact=True).count() == 1,
                 'the star did not flip at once')
        tab.page.wait_for_timeout(120)
        changed = tab.now()
        click_old(tab.page, 'window', f"{moved['window']}h")
        tab.page.wait_for_timeout(1500 if variant == 'A' else 100)
        mid = tab.snap()
        released = tab.now()
        if held:
            held[0].continue_()
        tab.quiet(2000, 60)
        rec = tab.record()
        s = tab.snap()
        c.number('filter moved ms after the star', round(changed - starred))
        c.number('mark held ms (star to release)', round(released - starred))
        c.number('mark released ms after the filter moved', round(released - changed))
        c.number('on screen when released', f"{len(mid['rows'])} rows,"
                 f" controls {mid['controls']}, busy {mid['busy']}")
        address = query_of(tab.page.url)
        c.number('address bar', f"window={address.get('window')}"
                 f" segment={address.get('segment')!r} t={address.get('t')}")
        c.expect(triple(address) == triple(moved),
                 f'the address bar kept {triple(address)}')
        asked = board_requests(rec, since=changed)
        c.r['requests_after_change'] = [(label_of_url(r['url']),
                                         round(r['t0'] - changed), is_poll(r))
                                        for r in asked]
        c.number('board requests after the filter moved',
                 [f'{label_of_url(r["url"])}@{round(r["t0"] - changed)}ms'
                  for r in asked])
        c.expect(asked and all(triple(query_of(r['url'])) == triple(moved)
                               for r in asked),
                 'a board request after the move was for the old selection')
        marks = [r for r in rec['requests'] if '/radar/api/watch/' in r['url']]
        c.expect(marks and marks[-1]['status'] == 200,
                 f'the mark answered {marks[-1]["status"] if marks else None}')
        board = stored(moved)
        expected = {row['ticker'] for row in board['rows'] or []} | {
            row['ticker'] for row in board['watch_rows'] or []}
        c.expect(set(s['rows']) == expected,
                 'the rows on screen are not the new selection\'s')
        c.expect(ticker in (board['watching'] or []), 'the mark was not saved')
        c.expect(tab.page.get_by_role('button', name=f'Stop watching {ticker}',
                                      exact=True).count() == 1,
                 'the star is not on after the refetch')
        last = [r for r in board_requests(rec) if r['board'] is not None][-1]
        c.expect(str(last['board']['window']) == moved['window']
                 and ticker in last['board']['watching'],
                 'the last board answer is not the new selection with the mark')
        c.expect(context_window('old', s) in (None, int(moved['window'])),
                 f'the rendered window is {context_window("old", s)}h')
        c.shot(tab, f'8b-8-old-star-{variant}.png',
               f'star {variant}: the new selection, the mark kept, the address'
               ' bar on the new query')
        tab.page.unroute('**/radar/api/watch/**')


# --- phone ----------------------------------------------------------------------------------

def phone_shots(stack, browser, cookie):
    ctx = new_context(browser, cookie, PHONE, phone=True)
    try:
        for kind, args in (('old', COLD['phone_old']), ('hub', COLD['phone_hub'])):
            with checking('m', kind, f'390x844 ({label(args)})') as c:
                make_cold(args)
                tab = Tab(ctx, url_for(kind, stack.base(), args), kind)
                c.tabs.append(tab)
                tab.wait(WAITING, 30)
                # Where the reader is: the scroll offset, what holds focus, and
                # where the old board's detail panel sits in the viewport.
                where = ("() => { const d = document.querySelector("
                         "'main.detail'); const a = document.activeElement;"
                         " return { y: Math.round(window.scrollY),"
                         " active: a ? a.tagName + '.' + a.className : null,"
                         " panel_top: d ? Math.round("
                         "d.getBoundingClientRect().top) : null }; }")
                c.number('while pending: scroll, focus, panel top',
                         tab.page.evaluate(where))
                c.shot(tab, f'8b-m-{kind}-pending-390.png',
                       'phone, 390x844: pending')
                tab.wait(ROWS_READY, 180)
                rows_at = tab.record()['firstRowsAt']
                c.number('time to rows s', seconds(rows_at))
                c.number('right after the rows: scroll, focus, panel top',
                         tab.page.evaluate(where))
                # Usable is the old board's panel settled for its ticker: the
                # panel takes focus when that detail loads, and on this layout
                # focus scrolls. Measured after it, plus a second for a smooth
                # scroll to finish -- not at a fixed delay after the rows,
                # which in run 2 came before the detail had loaded.
                tab.wait(USABLE, 90)
                tab.page.wait_for_timeout(1000)
                c.number('usable s after the rows',
                         seconds(tab.record()['usableAt'] - rows_at))
                c.number('panel settled: scroll, focus, panel top',
                         tab.page.evaluate(where))
                c.shot(tab, f'8b-m-{kind}-ready-390.png',
                       'phone, 390x844: where the page is once the board'
                       ' and its panel have arrived')
    finally:
        ctx.close()


# --- the ledger's tables, from a saved run ------------------------------------------

CHECK_NAMES = {'1': 'empty store', '2': 'rapid switching', '3': 'hidden tab',
               '4': 'stale to fresh', '5': 'hard-expired', '6': 'delayed',
               '7': 'flag off', '8': 'the star', 'm': 'phone, 390x844'}


def _cell(value):
    if value is None:
        return 'n/a'
    if isinstance(value, bool):
        return 'yes' if value else 'no'
    if isinstance(value, list):
        return ', '.join(_cell(item) for item in value) or '(none)'
    return str(value).replace('|', '/')


def tables(path):
    """Markdown for the ledger, derived from `browser_perf3.json`: one table
    per check with every number it recorded, then what failed, the notes, the
    screenshots and the observations."""
    record = json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
    results = record['results']
    order = ['1', '2', '3', '4', '5', '6', '7', '8', 'm']
    print(f"Run: namespace `{record['namespace'][:12]}`, revision"
          f" `{record['revision'][:12]}`, {record['minutes']} minutes.\n")
    print('| check | page | case | verdict |')
    print('| --- | --- | --- | --- |')
    for number in order:
        for r in (r for r in results if r['check'] == number):
            print(f"| {number} {CHECK_NAMES[number]} | {r['page']} |"
                  f" {_cell(r['title'])} | **{r['verdict']}** |")
    for number in order:
        group = [r for r in results if r['check'] == number]
        if not group:
            continue
        keys = []
        for r in group:
            keys += [k for k in r['numbers'] if k not in keys]
        print(f"\n#### {number}: {CHECK_NAMES[number]}\n")
        print('| page | case | ' + ' | '.join(keys) + ' |')
        print('| --- | --- | ' + ' | '.join('---' for _ in keys) + ' |')
        for r in group:
            print(f"| {r['page']} | {_cell(r['title'])} | "
                  + ' | '.join(_cell(r['numbers'].get(k)) for k in keys) + ' |')
        for r in group:
            for failure in r['failures']:
                print(f"\n- FAILED [{r['page']}] {failure}")
            for note in r['notes']:
                print(f"\n- note [{r['page']}] {note}")
            if r.get('violations'):
                print(f"\n- violations [{r['page']}] {r['violations']}")
            if r.get('page_errors'):
                print(f"\n- page console [{r['page']}] "
                      + '; '.join(sorted(set(r['page_errors']))[:6]))
    print('\n#### Screenshots\n')
    print('| file | what it shows |')
    print('| --- | --- |')
    for number in order:
        for r in (r for r in results if r['check'] == number):
            for shot in r['shots']:
                print(f"| `{shot['file']}` | {shot['what']} |")
    for note in record.get('observations', []):
        print(f'\nobservation: {json.dumps(note, default=str)}')


# --- main ------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--checks', default='1,2,4,5,8,m,3,6,7')
    parser.add_argument('--out', default=None)
    parser.add_argument('--tables', default=None, metavar='JSON',
                        help="print the ledger's tables from a saved run")
    args = parser.parse_args()
    wanted = set(args.checks.split(','))
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if args.tables:
        tables(args.tables)
        return 0

    facts = env_check.preflight('browser_perf3 (Task 8b): both boards in a'
                                ' real browser')
    global APP, ENGINE, NS, UID
    APP = scale_env.bind()
    ENGINE = scale_env.engine()
    NS = scale_env.namespace()
    out = common.out_dir(args.out or common.DEFAULT_OUT.parent
                         / 'radar-perf3-task8b')
    from playwright.sync_api import sync_playwright

    warm = {common.key_of(a)[0] for a in common.warm_args()}
    used = [US_ALL_24, US_ALL_12, *COLD.values()]
    for start, steps in SWITCH.values():
        used += [start] + [step[3] for step in steps]
    seen = set()
    print('\nselections (key, warm?)')
    for a in used:
        if label(a) in seen:
            continue
        seen.add(label(a))
        print(f'  {label(a):22s} {key(a)[:12]}  {"warm" if key(a) in warm else "cold"}')
    if key(US_ALL_24) not in warm or key(US_ALL_12) not in warm:
        raise SystemExit('the explicit-sources URL does not reach the warm key')
    for name in ('hidden_old', 'hidden_hub', 'delayed_old', 'delayed_hub',
                 'phone_old', 'phone_hub'):
        if key(COLD[name]) in warm:
            raise SystemExit(f'{name} is a warm key')

    UID = common.create_accounts(ENGINE, {USER: []})[USER]
    cookie = common.mint_cookie(APP, UID)
    print(f'minted a session cookie for {USER} (id {UID}); no password used')
    stack = Stack(out)
    began = time.perf_counter()
    try:
        stack.start_producer()
        stack.start_server('on', PORT_ON)
        print(f'server {stack.base()} flag=on; producer pid {stack.producer.pid}')
        print(f'prewarm: {ready_idle():.1f} s until eight fresh warm boards')
        with sync_playwright() as p:
            browser = p.chromium.launch()
            print(f'chromium {browser.version}')
            ctx = new_context(browser, cookie, VIEWPORT)
            if '1' in wanted:
                for kind in ('old', 'hub'):
                    check_empty(stack, ctx, kind)
            if '2' in wanted:
                for variant in ('ready', 'pending'):
                    for kind in ('old', 'hub'):
                        check_switching(stack, ctx, kind, variant)
                try:
                    discover_key_note()
                except Exception as problem:              # noqa: BLE001
                    print(f'observation failed: {problem!r}', flush=True)
            if '4' in wanted:
                check_stale(stack, ctx, 'old', US_ALL_24)
                check_stale(stack, ctx, 'hub', US_ALL_12)
            if '5' in wanted:
                check_expired(stack, ctx, 'old', US_ALL_12)
                check_expired(stack, ctx, 'hub', US_ALL_24)
            if '8' in wanted:
                clear_watches()
                check_star(stack, ctx, 'A', US_ALL_24, US_ALL_12, 2)
                check_star(stack, ctx, 'B', US_ALL_12, US_ALL_24, 4)
                clear_watches()
            if 'm' in wanted:
                phone_shots(stack, browser, cookie)
            if '3' in wanted or '6' in wanted:
                stack.stop_producer()
                if '3' in wanted:
                    check_hidden(stack, ctx, 'old', COLD['hidden_old'])
                    check_hidden(stack, ctx, 'hub', COLD['hidden_hub'])
                if '6' in wanted:
                    check_delayed(stack, ctx)
                if stack.producer is None:
                    stack.start_producer()
            if '7' in wanted:
                check_flag_off(stack, ctx)
            ctx.close()
            browser.close()
    finally:
        stack.stop_all()
        removed = common.delete_accounts(ENGINE, [USER])
        rows, others = common.delete_on_demand(ENGINE, NS)
        print(f'\ncleanup: {removed} account(s); {rows} on-demand board(s) and'
              f' {others} row(s) of other namespaces deleted')
        record = {'facts': facts, 'namespace': NS,
                  'revision': os.environ['PERF3_REVISION'],
                  'results': RESULTS, 'observations': OBSERVATIONS,
                  'logs': stack.logs,
                  'minutes': round((time.perf_counter() - began) / 60, 1)}
        common.save(out, 'browser_perf3.json', record)

    print('\n' + '=' * 72)
    print(f'{"check":6s} {"page":5s} {"verdict":8s} title')
    for r in RESULTS:
        print(f"{r['check']:6s} {r['page']:5s} {r['verdict']:8s} {r['title']}")
        for failure in r['failures']:
            print(f'{"":21s}FAIL {failure}')
    failed = [r for r in RESULTS if r['verdict'] != 'PASS']
    print(f'{len(RESULTS) - len(failed)} of {len(RESULTS)} passed')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
