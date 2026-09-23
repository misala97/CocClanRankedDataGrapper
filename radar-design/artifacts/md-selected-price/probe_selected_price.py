"""MD-SELECTED-PRICE-EVIDENCE-1 bounded provider probe.

Read-only research probe. Sequential requests, >= 2 s apart, 15 s timeout,
one fixed ordinary configuration (User-Agent 'Mozilla/5.0', Accept json, no
Origin/Referer, no cookies, no retries, no header/IP rotation). Stops a
provider on 401/403/429 and records Retry-After. Hard ceiling 48 requests.
Credentials: FINNHUB_API_KEY read from the repository root .env through
python-dotenv; never printed or written.
"""
import collections
import datetime as dt
import json
import os
import time
import zoneinfo
from pathlib import Path

import requests
from dotenv import dotenv_values

HERE = Path(__file__).resolve().parent
ROOT_ENV = Path(r'C:/Users/michi/Desktop/CodingStuff/.env')
ET = zoneinfo.ZoneInfo('America/New_York')
UA = 'Mozilla/5.0'
TIMEOUT = 15
GAP = 2.0
CEILING = 48

secrets = dotenv_values(ROOT_ENV) if ROOT_ENV.exists() else {}
FINNHUB_KEY = secrets.get('FINNHUB_API_KEY') or os.getenv('FINNHUB_API_KEY')

session = requests.Session()
session.headers.update({'User-Agent': UA, 'Accept': 'application/json'})
session.trust_env = False  # no proxies/netrc from the environment

stopped = set()
count = 0
log = []
raw = {}


def et(ms=None, s=None):
    stamp = (ms / 1000.0) if ms is not None else s
    return dt.datetime.fromtimestamp(stamp, ET).isoformat()


def request(provider, name, method, url, *, params=None, redact=()):
    global count
    if provider in stopped:
        log.append({'name': name, 'provider': provider, 'skipped': 'provider stopped'})
        return None
    if count >= CEILING:
        log.append({'name': name, 'provider': provider, 'skipped': 'ceiling'})
        return None
    if count:
        time.sleep(GAP)
    count += 1
    shown = {k: ('<redacted>' if k in redact else v) for k, v in (params or {}).items()}
    row = {'n': count, 'name': name, 'provider': provider, 'url': url, 'params': shown,
           'sent_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    t0 = time.monotonic()
    try:
        r = session.request(method, url, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        row.update(error=type(exc).__name__ + ': ' + str(exc)[:200],
                   elapsed_s=round(time.monotonic() - t0, 3))
        log.append(row)
        print('[%d] %s: ERROR %s' % (count, name, row['error']), flush=True)
        return None
    row.update(status=r.status_code, elapsed_s=round(time.monotonic() - t0, 3),
               bytes=len(r.content),
               headers={k: r.headers.get(k) for k in
                        ('Content-Type', 'Date', 'Retry-After', 'X-RateLimit-Limit',
                         'X-RateLimit-Remaining', 'X-RateLimit-Reset', 'Cache-Control')
                        if r.headers.get(k) is not None})
    if r.status_code in (401, 403, 429):
        stopped.add(provider)
        row['stopped_provider'] = True
        row['body_head'] = r.text[:200]
        log.append(row)
        print('[%d] %s: %d -> provider %s STOPPED' % (count, name, r.status_code, provider), flush=True)
        return None
    try:
        payload = r.json()
    except ValueError:
        row['body_head'] = r.text[:200]
        log.append(row)
        print('[%d] %s: %d non-JSON' % (count, name, r.status_code), flush=True)
        return None
    log.append(row)
    print('[%d] %s: %d %.3fs %dB' % (count, name, r.status_code, row['elapsed_s'], row['bytes']), flush=True)
    return payload


def spacing(stamps_s):
    if len(stamps_s) < 2:
        return {}
    gaps = collections.Counter(b - a for a, b in zip(stamps_s, stamps_s[1:]))
    return {str(k): v for k, v in sorted(gaps.items(), key=lambda kv: -kv[1])[:6]}


def summarize_nasdaq_chart(name, payload):
    out = {'name': name}
    data = payload.get('data') if isinstance(payload, dict) else None
    out['status_block'] = payload.get('status') if isinstance(payload, dict) else None
    out['message'] = payload.get('message') if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        out['data'] = data
        return out
    out['data_keys'] = sorted(data.keys())
    for k in ('symbol', 'company', 'timeAsOf', 'isNasdaq100', 'lastSalePrice',
              'netChange', 'percentageChange', 'deltaIndicator', 'previousClose'):
        if k in data:
            out[k] = data[k]
    pts = data.get('chart') or []
    out['count'] = len(pts)
    if not pts:
        return out
    xs = [p.get('x') for p in pts]
    out['first_et'] = et(ms=xs[0])
    out['last_et'] = et(ms=xs[-1])
    out['first_x'] = xs[0]
    out['last_x'] = xs[-1]
    out['z_keys'] = sorted((pts[0].get('z') or {}).keys())
    out['distinct_et_dates'] = sorted({dt.datetime.fromtimestamp(x / 1000, ET).date().isoformat() for x in xs})
    out['spacing_seconds'] = spacing([x // 1000 for x in xs])
    out['null_y'] = sum(1 for p in pts if p.get('y') is None)
    out['nonpositive_y'] = sum(1 for p in pts if isinstance(p.get('y'), (int, float)) and p['y'] <= 0)
    out['monotonic_x'] = all(a < b for a, b in zip(xs, xs[1:]))
    out['samples'] = pts[:2] + pts[len(pts) // 2:len(pts) // 2 + 1] + pts[-2:]
    raw[name] = pts
    return out


def summarize_nasdaq_info(name, payload):
    out = {'name': name}
    data = payload.get('data') if isinstance(payload, dict) else None
    out['status_block'] = payload.get('status') if isinstance(payload, dict) else None
    out['message'] = payload.get('message') if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        out['data'] = data
        return out
    out['data_keys'] = sorted(data.keys())
    for k in ('symbol', 'companyName', 'stockType', 'exchange', 'isNasdaqListed',
              'isNasdaq100', 'isHeld', 'marketStatus', 'assetClass'):
        out[k] = data.get(k)
    out['primaryData'] = data.get('primaryData')
    out['secondaryData'] = data.get('secondaryData')
    ks = data.get('keyStats') or {}
    out['keyStats_keys'] = sorted(ks.keys()) if isinstance(ks, dict) else None
    p = data.get('primaryData') or {}
    ts = p.get('lastTradeTimestamp')
    if isinstance(ts, str):
        for fmt in ('%b %d, %Y %I:%M %p ET', '%b %d, %Y'):
            try:
                naive = dt.datetime.strptime(ts.replace('  ', ' '), fmt)
                out['lastTrade_parsed_et'] = naive.replace(tzinfo=ET).isoformat()
                out['lastTrade_epoch'] = int(naive.replace(tzinfo=ET).timestamp())
                break
            except ValueError:
                continue
    return out


def summarize_yahoo(name, payload):
    out = {'name': name}
    chart = payload.get('chart') if isinstance(payload, dict) else None
    if not isinstance(chart, dict):
        out['payload_keys'] = list(payload.keys()) if isinstance(payload, dict) else None
        return out
    out['error'] = chart.get('error')
    results = chart.get('result')
    if not results:
        return out
    res = results[0]
    meta = res.get('meta') or {}
    out['meta'] = {k: meta.get(k) for k in (
        'symbol', 'currency', 'exchangeName', 'fullExchangeName', 'instrumentType',
        'exchangeTimezoneName', 'gmtoffset', 'timezone', 'regularMarketPrice',
        'regularMarketTime', 'chartPreviousClose', 'previousClose', 'dataGranularity',
        'range', 'validRanges', 'hasPrePostMarketData', 'firstTradeDate')}
    ctp = meta.get('currentTradingPeriod') or {}
    out['currentTradingPeriod_regular'] = ctp.get('regular')
    ts = res.get('timestamp') or []
    q = ((res.get('indicators') or {}).get('quote') or [{}])[0]
    adj = ((res.get('indicators') or {}).get('adjclose') or [{}])[0]
    out['count'] = len(ts)
    out['quote_keys'] = sorted(q.keys())
    out['has_adjclose'] = bool(adj.get('adjclose'))
    if ts:
        tz = zoneinfo.ZoneInfo(meta.get('exchangeTimezoneName') or 'America/New_York')
        out['first'] = dt.datetime.fromtimestamp(ts[0], tz).isoformat()
        out['last'] = dt.datetime.fromtimestamp(ts[-1], tz).isoformat()
        out['distinct_dates'] = sorted({dt.datetime.fromtimestamp(t, tz).date().isoformat() for t in ts})
        out['spacing_seconds'] = spacing(ts)
        closes = q.get('close') or []
        out['null_close'] = sum(1 for c in closes if c is None)
        out['len_close_eq_ts'] = len(closes) == len(ts)
        out['null_volume'] = sum(1 for v in (q.get('volume') or []) if v is None)
        by_date = collections.Counter(dt.datetime.fromtimestamp(t, tz).date().isoformat() for t in ts)
        out['points_per_date'] = dict(sorted(by_date.items()))
        n = len(ts)
        idx = [i for i in (0, 1, n // 2, n - 2, n - 1) if 0 <= i < n]
        def col(key, i):
            arr = q.get(key) or []
            return arr[i] if i < len(arr) else None
        out['samples'] = [{'ts': ts[i], 'local': dt.datetime.fromtimestamp(ts[i], tz).isoformat(),
                           'o': col('open', i), 'h': col('high', i), 'l': col('low', i),
                           'c': col('close', i), 'v': col('volume', i)} for i in idx]
        raw[name] = {'timestamp': ts, 'quote': q}
    return out


def summarize_finnhub(name, payload, sent_utc):
    out = {'name': name, 'payload': payload}
    if isinstance(payload, dict) and isinstance(payload.get('t'), (int, float)):
        out['t_et'] = et(s=payload['t'])
        sent = dt.datetime.fromisoformat(sent_utc)
        out['age_at_request_s'] = round(sent.timestamp() - payload['t'], 1)
    return out


# Sample. Identity from Nasdaq Trader listing files dated 2026-08-24
# (personal_apps/nasdaqlisted.txt, otherlisted.txt) -- not verified current.
SAMPLE = [
    # ticker, nasdaq symbol, nasdaq assetclass, yahoo symbol, finnhub symbol, why
    ('AAPL', 'AAPL', 'stocks', 'AAPL', 'AAPL', 'Nasdaq Global Select common; continuity with saved 2026-09-09 probe'),
    ('GE', 'GE', 'stocks', 'GE', 'GE', 'NYSE common; continuity with saved TradingView sample'),
    ('SPY', 'SPY', 'etf', 'SPY', 'SPY', 'NYSE Arca ETF (otherlisted ETF=Y, exchange P); assetclass=etf path'),
    ('RZLV', 'RZLV', 'stocks', 'RZLV', 'RZLV', 'Nasdaq Global Market small stock; used in original comparison'),
    ('BRK.B', 'BRK.B', 'stocks', 'BRK-B', 'BRK.B', 'NYSE class share; dot/hyphen symbol edge case across providers'),
]
today = dt.datetime.now(ET).date()
summary = {'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
           'started_et': dt.datetime.now(ET).isoformat(),
           'config': {'user_agent': UA, 'accept': 'application/json', 'timeout_s': TIMEOUT,
                      'gap_s': GAP, 'ceiling': CEILING, 'origin_referer': False,
                      'cookies': False, 'retries': False, 'proxies': False,
                      'finnhub_key_present': bool(FINNHUB_KEY)},
           'sample': [dict(zip(('ticker', 'nasdaq', 'assetclass', 'yahoo', 'finnhub', 'why'), s)) for s in SAMPLE],
           'results': []}

for ticker, nsym, aclass, ysym, fsym, why in SAMPLE:
    block = {'ticker': ticker}
    p = request('nasdaq', 'nasdaq_chart_undated_' + ticker, 'GET',
                'https://api.nasdaq.com/api/quote/%s/chart' % nsym, params={'assetclass': aclass})
    if p is not None:
        block['nasdaq_chart_undated'] = summarize_nasdaq_chart('nasdaq_chart_undated_' + ticker, p)
        if ticker == 'BRK.B' and block['nasdaq_chart_undated'].get('count', 0) == 0:
            p2 = request('nasdaq', 'nasdaq_chart_undated_BRK-B_alt', 'GET',
                         'https://api.nasdaq.com/api/quote/BRK-B/chart', params={'assetclass': aclass})
            if p2 is not None:
                block['nasdaq_chart_undated_alt_BRK-B'] = summarize_nasdaq_chart('nasdaq_chart_undated_BRK-B_alt', p2)
    p = request('nasdaq', 'nasdaq_chart_dated9d_' + ticker, 'GET',
                'https://api.nasdaq.com/api/quote/%s/chart' % nsym,
                params={'assetclass': aclass, 'fromdate': (today - dt.timedelta(days=9)).isoformat(),
                        'todate': today.isoformat()})
    if p is not None:
        block['nasdaq_chart_dated9d'] = summarize_nasdaq_chart('nasdaq_chart_dated9d_' + ticker, p)
    p = request('nasdaq', 'nasdaq_info_' + ticker, 'GET',
                'https://api.nasdaq.com/api/quote/%s/info' % nsym, params={'assetclass': aclass})
    info_sent = log[-1].get('sent_utc') if log else None
    if p is not None:
        block['nasdaq_info'] = summarize_nasdaq_info('nasdaq_info_' + ticker, p)
        block['nasdaq_info']['sent_utc'] = info_sent
    p = request('yahoo', 'yahoo_5d_5m_' + ticker, 'GET',
                'https://query1.finance.yahoo.com/v8/finance/chart/' + ysym,
                params={'range': '5d', 'interval': '5m', 'includePrePost': 'false'})
    if p is not None:
        block['yahoo_5d_5m'] = summarize_yahoo('yahoo_5d_5m_' + ticker, p)
    p = request('yahoo', 'yahoo_1d_1m_' + ticker, 'GET',
                'https://query1.finance.yahoo.com/v8/finance/chart/' + ysym,
                params={'range': '1d', 'interval': '1m', 'includePrePost': 'true'})
    if p is not None:
        block['yahoo_1d_1m'] = summarize_yahoo('yahoo_1d_1m_' + ticker, p)
    if FINNHUB_KEY:
        p = request('finnhub', 'finnhub_quote_' + ticker, 'GET',
                    'https://finnhub.io/api/v1/quote', params={'symbol': fsym, 'token': FINNHUB_KEY},
                    redact=('token',))
        if p is not None:
            block['finnhub_quote'] = summarize_finnhub('finnhub_quote_' + ticker, p, log[-1]['sent_utc'])
    else:
        block['finnhub_quote'] = {'skipped': 'no local FINNHUB_API_KEY'}
    summary['results'].append(block)

# Empty / invalid behaviour, one symbol that does not exist.
block = {'ticker': 'ZZZZZZ (nonexistent)'}
p = request('nasdaq', 'nasdaq_chart_undated_ZZZZZZ', 'GET',
            'https://api.nasdaq.com/api/quote/ZZZZZZ/chart', params={'assetclass': 'stocks'})
if p is not None:
    block['nasdaq_chart_undated'] = summarize_nasdaq_chart('nasdaq_chart_undated_ZZZZZZ', p)
p = request('nasdaq', 'nasdaq_info_ZZZZZZ', 'GET',
            'https://api.nasdaq.com/api/quote/ZZZZZZ/info', params={'assetclass': 'stocks'})
if p is not None:
    block['nasdaq_info'] = summarize_nasdaq_info('nasdaq_info_ZZZZZZ', p)
p = request('yahoo', 'yahoo_5d_5m_ZZZZZZ', 'GET',
            'https://query1.finance.yahoo.com/v8/finance/chart/ZZZZZZ',
            params={'range': '5d', 'interval': '5m', 'includePrePost': 'false'})
if p is not None:
    block['yahoo_5d_5m'] = summarize_yahoo('yahoo_5d_5m_ZZZZZZ', p)
if FINNHUB_KEY:
    p = request('finnhub', 'finnhub_quote_ZZZZZZ', 'GET', 'https://finnhub.io/api/v1/quote',
                params={'symbol': 'ZZZZZZ', 'token': FINNHUB_KEY}, redact=('token',))
    if p is not None:
        block['finnhub_quote'] = summarize_finnhub('finnhub_quote_ZZZZZZ', p, log[-1]['sent_utc'])
summary['results'].append(block)

summary['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
summary['request_count'] = count
summary['providers_stopped'] = sorted(stopped)
summary['request_log'] = log
(HERE / 'probe_summary.json').write_text(json.dumps(summary, indent=2, default=str), encoding='utf-8')
(HERE / 'probe_raw_points.json').write_text(json.dumps(raw, default=str), encoding='utf-8')
print('requests:', count, 'stopped:', sorted(stopped))
