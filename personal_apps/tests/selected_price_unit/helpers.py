"""Shared fixtures for the DB-free selected-price suite (no app, no engine,
no network). Run from personal_apps:

    py -3.12 -m pytest tests/selected_price_unit --confcutdir=tests/selected_price_unit -q
"""
import datetime as dt

from features.radar import price_chart_contract as c

UTC = dt.timezone.utc


def utc(*parts):
    return dt.datetime(*parts, tzinfo=UTC)


def naive(*parts):
    return dt.datetime(*parts)


def company_row(**over):
    row = {'id': 11, 'symbol': 'AAPL', 'name': 'Apple Inc', 'first_seen': naive(2026, 1, 1),
           'delisted_at': None}
    row.update(over)
    return row


def instrument_row(**over):
    row = {'id': 7, 'ticker': 'AAPL', 'market': 'us', 'venue': 'NASDAQ', 'mic': 'XNMS',
           'provider_symbol': 'AAPL', 'currency': 'USD', 'is_primary': 1,
           'mapping_status': 'mapped', 'mapped_at': naive(2026, 8, 1)}
    row.update(over)
    return row


def identity(**over):
    base = {'ticker': 'AAPL', 'company_id': 11, 'instrument_id': 7, 'mic': 'XNMS',
            'venue': 'NASDAQ', 'currency': 'USD', 'provider_symbol': 'AAPL',
            'mapped_at_dt': naive(2026, 8, 1), 'first_seen_dt': naive(2026, 1, 1)}
    base.update(over)
    base['mapped_at'] = c.iso_z(base['mapped_at_dt'])
    base['fingerprint'] = c.fingerprint(base['company_id'], base['instrument_id'],
                                        base['provider_symbol'], base['currency'], base['mic'],
                                        base['mapped_at_dt'])
    return base


def bucket(when, source='bluesky', count=1, status='ok', config='v1'):
    return {'bucket_start': when, 'source': source, 'mention_count': count,
            'status': status, 'source_config_version': config}


def tone_row(when, source='bluesky', **counts):
    row = {'source': source, 'bucket_start': when, 'eligibility_conflicts': 0,
           'bullish': 0, 'bearish': 0, 'neutral': 0, 'unjudged': 0, 'unavailable': 0}
    row.update(counts)
    row['total'] = sum(row[k] for k in c.TONE_CATEGORIES)
    return row


def series(anchor, *, received_at, values=(101.0,), interval=300, source=c.YAHOO_SOURCE):
    return {'kind': 'ok', 'source': source,
            'bars': [[anchor + i * interval, v] for i, v in enumerate(values)],
            'off_grid': 0, 'outside': 0, 'nulls': 0, 'received_at': received_at}


def alpaca_series(anchor, *, received_at, values=(101.0,), interval=60):
    return series(anchor, received_at=received_at, values=values, interval=interval,
                  source=c.ALPACA_SOURCE)


class FakeStore:
    """Returns what it was given; the contract does the exclusions. The SQL
    filters themselves are proved against SQLite in test_reader.py."""

    def __init__(self, *, companies=None, instruments=None, buckets=(), quotes=(), daily=(),
                 tone=(), fail=None, log=None):
        self.companies = [company_row()] if companies is None else companies
        self.instruments = [instrument_row()] if instruments is None else instruments
        self.buckets, self.quotes, self.daily, self.tone = list(buckets), list(quotes), list(daily), list(tone)
        self.fail = fail or {}
        self.log = log if log is not None else []
        self.calls, self.params, self.timeouts = [], {}, {}

    def _call(self, name, timeout_s, **params):
        self.calls.append(name)
        self.log.append(name)
        self.params[name] = params
        self.timeouts[name] = timeout_s
        if name in self.fail:
            raise self.fail[name]

    def company_by_symbol(self, ticker, *, timeout_s):
        self._call('company_by_symbol', timeout_s, ticker=ticker)
        return [dict(r) for r in self.companies if r['symbol'] == ticker][:2]

    def primary_candidates(self, ticker, *, timeout_s):
        self._call('primary_candidates', timeout_s, ticker=ticker)
        return [dict(r) for r in self.instruments if r['ticker'] == ticker][:2]

    def bucket_rows(self, ticker, sources, start, end, *, timeout_s):
        self._call('bucket_rows', timeout_s, ticker=ticker, sources=list(sources), start=start, end=end)
        return [dict(r) for r in self.buckets]

    def quote_rows(self, ticker, mic, start, end, read_start, *, timeout_s):
        self._call('quote_rows', timeout_s, ticker=ticker, mic=mic, start=start, end=end,
                   read_start=read_start)
        return [dict(r) for r in self.quotes]

    def daily_rows(self, ticker, mic, from_date, to_date, read_start, *, timeout_s):
        self._call('daily_rows', timeout_s, ticker=ticker, mic=mic, from_date=from_date,
                   to_date=to_date, read_start=read_start)
        return [dict(r) for r in self.daily]

    def tone_rows(self, ticker, sources, lower, upper, *, timeout_s):
        self._call('tone_rows', timeout_s, ticker=ticker, sources=list(sources), lower=lower, upper=upper)
        return [dict(r) for r in self.tone]


class FakeAdmission:
    def __init__(self, *answers, log=None):
        self.answers = list(answers) or [{'state': 'disabled', 'retry_after_seconds': None,
                                          'reason': 'off', 'series': None}]
        self.log = log if log is not None else []
        self.calls = []

    def get_or_start(self, identity, window, *, now):
        self.calls.append((identity['fingerprint'], window))
        self.log.append('admission')
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]


class Clock:
    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now
