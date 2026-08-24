# personal_apps/tests/test_radar_profile_order.py
"""Which tickers the profile job spends its calls on.

`_loud_tickers` ranks the candidate pool by mention_z. `_profiles_due` then
filtered that pool with `WHERE symbol IN (...)` and no ORDER BY, so the
database's scan order -- symbol order, in practice -- decided who got a
profile and who waited.

Found in production 2026-08-24: 167 eligible tickers against a limit of 40,
and SPY, QQQ and TSLA had been in the pool for three days, eligible on every
six-hourly pass, losing the cut every time to whatever new names arrived
between A and N. All three rendered as segment Unknown the whole time, which
put Netflix and Tesla under the Small tab.

Every other test of this path monkeypatches `_profiles_due` itself. That is
why the bug shipped: the function that chooses was the one nothing exercised.
"""
import datetime as dt

import pytest

import run_radar_ingest as daemon
from app import app as flask_app
from extensions import db
from models import TickerUniverse

PREFIX = 'TPO'
NOW = dt.datetime(2026, 8, 24, 12, tzinfo=dt.timezone.utc)


@pytest.fixture()
def clean():
    def wipe():
        TickerUniverse.query.filter(
            TickerUniverse.symbol.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def universe(suffix, refreshed_at=None, is_etf=None):
    symbol = f'{PREFIX}{suffix}'
    db.session.add(TickerUniverse(
        symbol=symbol, name=f'{symbol} Corp', exchange='N',
        is_etf=is_etf, first_seen=dt.datetime(2020, 1, 1),
        profile_refreshed_at=refreshed_at))
    return symbol


def test_the_loudest_eligible_ticker_is_picked_first(clean, monkeypatch):
    """The regression. Loudest first, whatever the symbols sort like.

    The pool is deliberately ordered against the alphabet: if the ranking is
    dropped anywhere, the database hands back AAA and BBB and this fails.
    """
    for suffix in ('AAA', 'BBB', 'CCC', 'DDD', 'ZZZ'):
        universe(suffix)
    db.session.commit()

    loudest_first = [f'{PREFIX}{s}' for s in ('ZZZ', 'DDD', 'AAA', 'BBB', 'CCC')]
    monkeypatch.setattr(daemon, '_loud_tickers',
                        lambda now, limit: loudest_first)

    assert daemon._profiles_due(NOW, 2) == [f'{PREFIX}ZZZ', f'{PREFIX}DDD']


def test_a_ticker_profiled_recently_is_skipped_and_a_quieter_one_takes_it(
        clean, monkeypatch):
    """Teeth for the test above: proves the order is not simply the pool's.

    Without this, returning the pool verbatim would pass the first test while
    ignoring eligibility entirely.
    """
    universe('ZZZ', refreshed_at=NOW.replace(tzinfo=None) - dt.timedelta(days=1))
    universe('DDD')
    universe('AAA')
    db.session.commit()

    loudest_first = [f'{PREFIX}{s}' for s in ('ZZZ', 'DDD', 'AAA')]
    monkeypatch.setattr(daemon, '_loud_tickers',
                        lambda now, limit: loudest_first)

    assert daemon._profiles_due(NOW, 2) == [f'{PREFIX}DDD', f'{PREFIX}AAA']


def test_a_stale_profile_becomes_eligible_again(clean, monkeypatch):
    old = NOW.replace(tzinfo=None) - dt.timedelta(
        days=daemon.PROFILE_MAX_AGE_DAYS + 1)
    universe('ZZZ', refreshed_at=old)
    db.session.commit()

    monkeypatch.setattr(daemon, '_loud_tickers',
                        lambda now, limit: [f'{PREFIX}ZZZ'])

    assert daemon._profiles_due(NOW, 40) == [f'{PREFIX}ZZZ']


def test_nothing_loud_asks_the_database_nothing(clean, monkeypatch):
    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: [])

    assert daemon._profiles_due(NOW, 40) == []


def test_a_known_fund_is_never_queued_for_a_profile(clean, monkeypatch):
    """There is nothing to fetch. Finnhub returns an empty payload for every
    ETF, so each one costs a slot to learn nothing -- and 5,636 of the 12,599
    rows in the live universe are funds, which is 140 runs of the queue.
    """
    universe('FUND', is_etf=True)
    universe('STOCK', is_etf=False)
    universe('UNREAD')
    db.session.commit()

    pool = [f'{PREFIX}{s}' for s in ('FUND', 'STOCK', 'UNREAD')]
    monkeypatch.setattr(daemon, '_loud_tickers', lambda now, limit: pool)

    due = daemon._profiles_due(NOW, 40)

    assert f'{PREFIX}FUND' not in due
    # Both of the others stay: not knowing is not the same as knowing it is a
    # fund, so a NULL is still asked.
    assert set(due) == {f'{PREFIX}STOCK', f'{PREFIX}UNREAD'}
