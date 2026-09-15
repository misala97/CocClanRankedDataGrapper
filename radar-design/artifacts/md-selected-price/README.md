# MD-SELECTED-PRICE-EVIDENCE-1 probe artifacts

Research-only artifacts for radar-design/MD-SELECTED-PRICE-EVIDENCE-1-RETURN.md. Local, uncommitted.

Request configuration (both scripts): `requests` 2.33.1 on Python 3.12.6, one `Session`, `User-Agent: Mozilla/5.0`, `Accept: application/json`, no Origin/Referer, no cookies, `trust_env=False` (no proxies), timeout 15 s, sequential with a 2 s gap, no retries, stop a provider on 401/403/429. Ceiling 48 data requests.

Ledger, 2026-09-15 (UTC):
- 13:50:04–13:52:00 `probe_selected_price.py` — 35 requests (Nasdaq 13, Yahoo 11, Finnhub 6 incl. one nonexistent symbol). Output `probe_summary.json` (per-request log with the token redacted, per-instrument summaries) and `probe_raw_points.json` (complete returned point arrays, public prices only).
- 13:56:16–13:56:28 `probe_supplement.py` — 4 Nasdaq requests. Output `probe_supplement.json`.
- Plus 3 `robots.txt` reads (www.nasdaq.com, api.nasdaq.com, query1.finance.yahoo.com) and documentation page reads (finnhub.io docs/terms, nasdaq.com/legal, legal.yahoo.com) that are not counted as data probes.

Total data requests: 39 of 48. No 401/403/429, no Retry-After observed.

Credential handling: `FINNHUB_API_KEY` read from the repository root `.env` via python-dotenv only inside the process; never printed or written.
