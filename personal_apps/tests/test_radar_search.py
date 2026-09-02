"""Search over the whole universe: symbol first, then names, eight at most."""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from models import RadarWatch, TickerUniverse
from features.radar import search
from conftest import _admin_id

TODAY = dt.date(2026, 9, 2)
# ZQ-prefixed so no real universe row can collide.
SEEDED = [
    ('ZQA',   'Zqa Widgets Inc',        'Q', '50000000000', None),
    ('ZQAB',  'Zqab Holdings',          'N', '900000000', None),
    ('ZQAA',  'Zqaa Tiny Co',           'Q', '1000000', None),
    ('ZQC',   'Other Name Corp',        'S', '4000000', None),
    ('ZQGONE','Zqa Delisted Co',        'Q', '1000000', dt.datetime(2026, 1, 1)),
    ('ZQZ',   'Something With zqa in',  'P', None, None),
]


@pytest.fixture()
def seeded():
    with flask_app.app_context():
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZQ%')).delete(
            synchronize_session=False)
        RadarWatch.query.filter(RadarWatch.ticker.like('ZQ%')).delete(
            synchronize_session=False)
        for symbol, name, exchange, cap, delisted in SEEDED:
            db.session.add(TickerUniverse(
                symbol=symbol, name=name, exchange=exchange,
                first_seen=dt.datetime(2026, 1, 1), delisted_at=delisted,
                market_cap=decimal.Decimal(cap) if cap else None))
        db.session.commit()
        yield
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZQ%')).delete(
            synchronize_session=False)
        RadarWatch.query.filter(RadarWatch.ticker.like('ZQ%')).delete(
            synchronize_session=False)
        db.session.commit()


def test_symbol_exact_then_prefix_then_name(seeded):
    with flask_app.app_context():
        found = [m.ticker for m in search.search_universe('zqa', TODAY)]
    # ZQA exact; then the prefix group by cap: ZQAB (900M) before ZQAA (1M);
    # then the name group. ZQGONE is delisted and never appears.
    assert found == ['ZQA', 'ZQAB', 'ZQAA', 'ZQZ']


def test_inside_a_group_the_bigger_company_comes_first(seeded):
    """Typing `nv` must surface NVDA, not the eight alphabetically-first
    NV* symbols: inside each group, market cap decides, then the symbol."""
    with flask_app.app_context():
        found = [m.ticker for m in search.search_universe('zqa', TODAY)]
    # ZQA exact; then the prefix group by cap: ZQAB (900M) before ZQAA (1M);
    # then the name group.
    assert found == ['ZQA', 'ZQAB', 'ZQAA', 'ZQZ']


def test_name_search_is_case_insensitive_and_carries_identity(seeded):
    with flask_app.app_context():
        [match] = search.search_universe('OTHER NAME', TODAY)
    assert match.ticker == 'ZQC'
    assert match.name == 'Other Name Corp'
    assert match.exchange == 'S'
    assert match.segment == 'micro'


def test_a_missing_cap_is_the_unknown_segment(seeded):
    with flask_app.app_context():
        [match] = search.search_universe('ZQZ', TODAY)
    assert match.segment == 'unknown'


def test_empty_and_overlong_queries(seeded):
    with flask_app.app_context():
        assert search.search_universe('', TODAY) == []
        assert search.search_universe('   ', TODAY) == []
        # Capped at 40 characters, so a pasted paragraph is a cheap query.
        assert search.search_universe('z' * 200, TODAY) == search.search_universe('z' * 40, TODAY)


def test_at_most_eight(seeded):
    with flask_app.app_context():
        assert len(search.search_universe('a', TODAY)) <= 8


def test_the_endpoint_marks_what_the_caller_watches(client, seeded):
    with flask_app.app_context():
        db.session.add(RadarWatch(user_id=_admin_id(), ticker='ZQAB',
                                  created_at=dt.datetime(2026, 9, 2)))
        db.session.commit()

    payload = client.get('/radar/api/search?q=zqa').get_json()

    by_ticker = {m['ticker']: m for m in payload['matches']}
    assert by_ticker['ZQAB']['watching'] is True
    assert by_ticker['ZQA']['watching'] is False
    assert set(by_ticker['ZQA']) == {'ticker', 'name', 'exchange', 'segment', 'watching'}


def test_the_endpoint_needs_a_session(anon_client):
    assert anon_client.get('/radar/api/search?q=zqa').status_code in (302, 401, 403)
