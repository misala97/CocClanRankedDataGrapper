"""Supplementary bounded probe (4 requests, same fixed configuration).

Questions left open by probe_selected_price.py:
1. Does a DATED Nasdaq chart request covering only today return intraday
   points or a daily bar? (fromdate = todate = today)
2. Does a dated two-day window return two sessions of intraday points?
3. Does the undated chart accept the slash spelling BRK/B for a class share?
Sequential, >= 2 s apart, 15 s timeout, User-Agent Mozilla/5.0, no retries.
"""
import datetime as dt
import json
import time
import zoneinfo
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ET = zoneinfo.ZoneInfo('America/New_York')
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
session.trust_env = False
today = dt.datetime.now(ET).date()
yesterday = today - dt.timedelta(days=1)

jobs = [
    ('nasdaq_chart_dated_today_AAPL', 'https://api.nasdaq.com/api/quote/AAPL/chart',
     {'assetclass': 'stocks', 'fromdate': today.isoformat(), 'todate': today.isoformat()}),
    ('nasdaq_chart_dated_2day_AAPL', 'https://api.nasdaq.com/api/quote/AAPL/chart',
     {'assetclass': 'stocks', 'fromdate': yesterday.isoformat(), 'todate': today.isoformat()}),
    ('nasdaq_chart_undated_BRK-slash-B', 'https://api.nasdaq.com/api/quote/BRK%2FB/chart',
     {'assetclass': 'stocks'}),
    ('nasdaq_chart_undated_BRK.B_second_sample', 'https://api.nasdaq.com/api/quote/BRK.B/chart',
     {'assetclass': 'stocks'}),
]
out = {'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'results': []}
for i, (name, url, params) in enumerate(jobs):
    if i:
        time.sleep(2.0)
    row = {'name': name, 'url': url, 'params': params,
           'sent_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
    t0 = time.monotonic()
    try:
        r = session.get(url, params=params, timeout=15)
        row['status'] = r.status_code
        row['elapsed_s'] = round(time.monotonic() - t0, 3)
        row['bytes'] = len(r.content)
        if r.status_code in (401, 403, 429):
            row['retry_after'] = r.headers.get('Retry-After')
            row['body_head'] = r.text[:200]
            out['results'].append(row)
            print(name, r.status_code, 'STOP')
            break
        payload = r.json()
        row['status_block'] = payload.get('status')
        data = payload.get('data')
        if isinstance(data, dict):
            pts = data.get('chart') or []
            row['data_keys'] = sorted(data.keys())
            row['timeAsOf'] = data.get('timeAsOf')
            row['count'] = len(pts)
            if pts:
                row['z_keys'] = sorted((pts[0].get('z') or {}).keys())
                row['first'] = pts[0]
                row['last'] = pts[-1]
                xs = [p['x'] for p in pts]
                row['distinct_x_dates_as_utc'] = sorted({
                    dt.datetime.fromtimestamp(x / 1000, dt.timezone.utc).date().isoformat() for x in xs})
        else:
            row['data'] = data
    except Exception as exc:
        row['error'] = type(exc).__name__ + ': ' + str(exc)[:200]
    out['results'].append(row)
    print(json.dumps(row, default=str)[:600])
out['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
(HERE / 'probe_supplement.json').write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
