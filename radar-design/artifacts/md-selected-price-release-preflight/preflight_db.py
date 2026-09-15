"""MD-SELECTED-PRICE-RELEASE-PREFLIGHT: bounded READ-ONLY MariaDB checks on existing data.
Uses the app's own DB credentials from /root/coc-stats/.env (never printed), pymysql,
one connection, READ ONLY transaction. EXPLAIN + a small fixed set of timed SELECTs for
ONE ticker/window, each under SET STATEMENT max_statement_time=1 FOR (the candidate
reader's mechanism). No writes, no DDL."""
import datetime as dt, json, re, sys, time
from pathlib import Path
SCRATCH = Path(sys.argv[1]); TICKER = sys.argv[2]
sys.path.insert(0, str(SCRATCH / 'personal_apps'))
from features.radar import price_chart_contract as c
import pymysql
env = {}
for line in Path('/root/coc-stats/.env').read_text().splitlines():
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1); env[k.strip()] = v.strip().strip('"').strip("'")
conn = pymysql.connect(host=env['DB_HOST'], user=env['DB_USER'], password=env['DB_PASS'],
                       database=env.get('PERSONAL_DB_NAME') or 'personal_apps',
                       cursorclass=pymysql.cursors.DictCursor, connect_timeout=5, read_timeout=15)
OUT = {'recorded_at_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'ticker': TICKER,
       'credentials': 'DB_USER/DB_PASS/DB_HOST from /root/coc-stats/.env (not printed)', 'driver': 'pymysql ' + pymysql.__version__}
cur = conn.cursor()
cur.execute('SET SESSION TRANSACTION READ ONLY'); cur.execute('START TRANSACTION READ ONLY')
cur.execute('SELECT VERSION() v, @@max_statement_time mst, @@session.max_statement_time smst, CURRENT_USER() u, @@tx_isolation iso')
OUT['session_before'] = cur.fetchone()
t0 = time.monotonic()
try:
    cur.execute('SET STATEMENT max_statement_time=1 FOR SELECT SLEEP(2) AS slept'); OUT['timeout_probe'] = {'error': None, 'row': cur.fetchone()}
except pymysql.err.OperationalError as e:
    OUT['timeout_probe'] = {'errno': e.args[0], 'message': e.args[1], 'elapsed_seconds': round(time.monotonic() - t0, 3)}
cur.execute('SELECT 1 AS recovered'); OUT['recovered_same_connection'] = cur.fetchone()
cur.execute('SELECT @@max_statement_time mst, @@session.max_statement_time smst'); OUT['session_after'] = cur.fetchone()
src = (SCRATCH / 'personal_apps/features/radar/price_chart_reader.py').read_text()
ana = (SCRATCH / 'personal_apps/features/radar/analysis.py').read_text()
def const(text, name):
    return re.search(name + r' = f?"""(.*?)"""', text, re.S).group(1)
CONFLICT = ''.join(re.findall(r'"([^"]*)"', re.search(r'_CONFLICT = \((.*?)\)\n', src, re.S).group(1)))
SQL = {'company_by_symbol': const(ana, 'COMPANY_BY_SYMBOL'), 'primary_candidates': const(ana, 'PRIMARY_CANDIDATES'),
       'bucket_rows': const(src, 'BUCKET_ROWS'), 'quote_rows': const(src, 'QUOTE_ROWS'), 'daily_rows': const(src, 'DAILY_ROWS'),
       'tone_rows': const(src, 'TONE_ROWS').replace('{_CONFLICT}', CONFLICT)}
NOW = dt.datetime.now(dt.timezone.utc); read_start = NOW.replace(tzinfo=None)
W1D, W1W = c.window_for('1D', NOW), c.window_for('1W', NOW)
OUT['windows'] = {s: {'from': w.start.isoformat(), 'to': w.end.isoformat(), 'sessions': [d.isoformat() for d in w.session_dates], 'waiting': w.waiting}
                  for s, w in (('1D', W1D), ('1W', W1W))}
cur.execute('SELECT id, mic, provider_symbol FROM radar_instruments WHERE ticker=%s AND market=%s AND is_primary=1 LIMIT 2', (TICKER, 'us'))
inst = cur.fetchall(); OUT['instrument'] = inst; MIC = inst[0]['mic']
cur.execute('SELECT DISTINCT source FROM radar_bucket_sources WHERE ticker=%s AND bucket_start>=%s AND bucket_start<%s LIMIT 65',
            (TICKER, W1W.start.replace(tzinfo=None), W1W.end.replace(tzinfo=None)))
SOURCES = [r['source'] for r in cur.fetchall()][:64]; OUT['sources_used'] = len(SOURCES)
def prep(sql, params):
    n = len(params.get('sources', []))
    text = sql.strip(); args = []
    for m in re.finditer(r'IN :sources|:(\w+)', text):
        if m.group(0) == 'IN :sources': args.extend(params['sources'])
        else: args.append(params[m.group(1)])
    if n: text = text.replace('IN :sources', 'IN (' + ','.join(['%s'] * n) + ')')
    text = re.sub(r':(\w+)', '%s', text)
    return text, args
retention_lower = max(W1W.start, NOW - dt.timedelta(hours=48)).replace(tzinfo=None)
N = lambda d: d.replace(tzinfo=None)
CASES = [
  ('company_by_symbol', {'ticker': TICKER}),
  ('primary_candidates', {'ticker': TICKER}),
  ('bucket_rows[1W]', {'ticker': TICKER, 'sources': SOURCES, 'window_start': N(W1W.start), 'window_end': N(W1W.end), 'row_limit': c.SOURCE_ROW_LIMIT + 1}),
  ('bucket_rows[1D]', {'ticker': TICKER, 'sources': SOURCES, 'window_start': N(W1D.start), 'window_end': N(W1D.end), 'row_limit': c.SOURCE_ROW_LIMIT + 1}),
  ('quote_rows[1D]', {'ticker': TICKER, 'mic': MIC, 'window_start': N(W1D.start), 'window_end': N(W1D.end), 'read_start': read_start, 'row_limit': c.QUOTE_ROW_LIMIT + 1}),
  ('daily_rows[1W]', {'ticker': TICKER, 'mic': MIC, 'from_date': W1W.session_dates[0], 'to_date': W1W.session_dates[-1], 'read_start': read_start, 'row_limit': c.DAILY_ROW_LIMIT + 1}),
  ('tone_rows[1W]', {'ticker': TICKER, 'sources': SOURCES, 'lower': retention_lower, 'upper': N(min(W1W.end, NOW)), 'row_limit': c.SOURCE_ROW_LIMIT + 1}),
]
BIG = {'radar_bucket_sources', 'radar_daily_closes', 'radar_mention_events', 'radar_posts', 'radar_mentions', 'radar_quotes'}
EXECUTE = {'company_by_symbol', 'primary_candidates', 'bucket_rows[1W]', 'quote_rows[1D]', 'daily_rows[1W]', 'tone_rows[1W]'}
OUT['checks'] = []
for name, params in CASES:
    base = name.split('[')[0]; text, args = prep(SQL[base], params)
    entry = {'name': name, 'param_count': len(args)}
    cur.execute('EXPLAIN ' + text, args); plan = cur.fetchall()
    entry['explain'] = [{k: r.get(k) for k in ('id', 'select_type', 'table', 'type', 'possible_keys', 'key', 'key_len', 'rows', 'Extra')} for r in plan]
    unsafe = any(r.get('type') == 'ALL' and (r.get('table') or '') in BIG for r in plan)
    entry['unsafe_full_scan_on_big_table'] = unsafe
    if name in EXECUTE and not unsafe:
        t0 = time.monotonic()
        try:
            cur.execute('SET STATEMENT max_statement_time=1.000 FOR ' + text, args); rows = cur.fetchall()
            entry['executed'] = {'rows': len(rows), 'elapsed_ms': round((time.monotonic() - t0) * 1000, 1)}
        except pymysql.err.OperationalError as e:
            entry['executed'] = {'errno': e.args[0], 'message': e.args[1], 'elapsed_ms': round((time.monotonic() - t0) * 1000, 1)}
    else:
        entry['executed'] = 'skipped' + (' (unsafe plan)' if unsafe else ' (EXPLAIN only)')
    OUT['checks'].append(entry)
cur.execute('SELECT @@session.max_statement_time smst'); OUT['session_end'] = cur.fetchone()
conn.rollback(); conn.close(); OUT['connection'] = 'closed'
print(json.dumps(OUT, indent=1, default=str))
