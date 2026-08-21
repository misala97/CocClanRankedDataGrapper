"""One ranked row per ticker, from everything the radar knows.

Reads scored buckets, quotes and universe rows. Decides nothing about
appearance -- that is Plan 5 -- but does decide what is worth showing at all,
which is the eligibility floor's job and the one place a thin board must not
be padded.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from models import RadarBucketSource, RadarQuote, TickerUniverse
from features.radar import leaderboard
from features.radar.config import source_config_version

NOW = dt.datetime(2026, 8, 21, 15, 0, 0)


@pytest.fixture()
def board():
    with flask_app.app_context():
        for model in (RadarBucketSource, RadarQuote):
            model.query.filter(model.ticker.like('LB%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('LB%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        for model in (RadarBucketSource, RadarQuote):
            model.query.filter(model.ticker.like('LB%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('LB%')).delete(
            synchronize_session=False)
        db.session.commit()


def universe_row(ticker, cap='50000000000', name='Test Corp'):
    db.session.add(TickerUniverse(
        symbol=ticker, name=name, exchange='NYSE',
        first_seen=dt.datetime(2020, 1, 1),
        market_cap=decimal.Decimal(cap) if cap else None))


def scored(ticker, source='bluesky', minutes_ago=30, mentions=10, authors=6,
           z=5.0, expected=1.0, variance=2.0, text_ratio=0.9, status='ok',
           baseline_days=30):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=NOW - dt.timedelta(minutes=minutes_ago),
        source=source, mention_count=mentions, high_confidence_count=mentions,
        low_count=0, distinct_authors=authors, distinct_text_ratio=text_ratio,
        engagement_weighted_count=float(mentions), status=status,
        source_config_version=source_config_version(),
        expected=expected, variance=variance, mention_z=z,
        baseline_days=baseline_days))


def quoted(ticker, price, prev, minutes_ago=5, quote_ts=None):
    when = NOW - dt.timedelta(minutes=minutes_ago)
    db.session.add(RadarQuote(
        ticker=ticker, fetched_at=when, quote_ts=quote_ts or when,
        price=decimal.Decimal(price), prev_close=decimal.Decimal(prev),
        volume=1000))


def test_a_scored_eligible_ticker_becomes_a_row(board):
    universe_row('LBA')
    scored('LBA')
    quoted('LBA', '100.00', '100.00')
    db.session.commit()

    rows = leaderboard.build_rows(['bluesky'], NOW)
    assert [r.ticker for r in rows] == ['LBA']
    assert rows[0].name == 'Test Corp'
    assert rows[0].mentions == 10


def test_an_ineligible_ticker_is_excluded_not_ranked_low(board):
    """Below the floor there is no signal to rank. Showing it at the bottom
    would imply it was measured and found wanting, when it was never
    measurable."""
    universe_row('LBB')
    scored('LBB', mentions=2, authors=1)
    db.session.commit()
    assert leaderboard.build_rows(['bluesky'], NOW) == []


def test_ranking_is_by_divergence(board):
    """Loud and unmoved outranks equally loud and already up."""
    universe_row('LBUP')
    universe_row('LBFLAT')
    for ticker in ('LBUP', 'LBFLAT'):
        scored(ticker)
    quoted('LBUP', '112.00', '100.00')     # ran hard
    quoted('LBFLAT', '100.20', '100.00')   # barely moved
    db.session.commit()

    rows = leaderboard.build_rows(['bluesky'], NOW)
    assert [r.ticker for r in rows] == ['LBFLAT', 'LBUP']


def test_only_the_selected_sources_are_pooled(board):
    """The selector is a read-time filter over stored components."""
    universe_row('LBC')
    scored('LBC', source='bluesky', mentions=6, z=3.0)
    scored('LBC', source='fourchan', mentions=6, z=3.0)
    db.session.commit()

    both = leaderboard.build_rows(['bluesky', 'fourchan'], NOW)[0]
    one = leaderboard.build_rows(['bluesky'], NOW)[0]
    assert both.mentions == 12
    assert one.mentions == 6
    assert both.mention_z > one.mention_z


def test_a_row_records_which_sources_contributed(board):
    universe_row('LBD')
    scored('LBD', source='bluesky')
    scored('LBD', source='fourchan')
    db.session.commit()
    row = leaderboard.build_rows(['bluesky', 'fourchan'], NOW)[0]
    assert set(row.sources) == {'bluesky', 'fourchan'}


def test_a_single_source_row_is_marked(board):
    """The same divergence backed by two independent sources is stronger
    evidence than one, and the row has to say which it is."""
    universe_row('LBE')
    scored('LBE', source='bluesky')
    db.session.commit()
    assert 'single-source' in leaderboard.build_rows(['bluesky', 'fourchan'],
                                                     NOW)[0].marks


def test_a_frozen_tape_carries_no_divergence(board):
    """A halted stock keeps its last price while mentions explode because it
    halted -- maximum divergence produced entirely by an artifact."""
    universe_row('LBF')
    scored('LBF')
    frozen = NOW - dt.timedelta(minutes=40)
    for step in range(3):
        quoted('LBF', '100.00', '100.00', minutes_ago=10 - 2 * step,
               quote_ts=frozen)
    db.session.commit()

    row = leaderboard.build_rows(['bluesky'], NOW)[0]
    assert row.divergence is None
    assert 'no-print' in row.marks


def test_a_ticker_with_no_quote_still_appears_without_divergence(board):
    """The chatter is real even when we have no price for it. Dropping the row
    would hide a genuine signal; inventing a divergence would fabricate one."""
    universe_row('LBG')
    scored('LBG')
    db.session.commit()
    row = leaderboard.build_rows(['bluesky'], NOW)[0]
    assert row.divergence is None
    assert row.price is None


def test_a_thin_baseline_is_marked_provisional(board):
    universe_row('LBH')
    scored('LBH', baseline_days=3)
    db.session.commit()
    assert 'provisional' in leaderboard.build_rows(['bluesky'], NOW)[0].marks


def test_a_truncated_source_is_marked_partial(board):
    universe_row('LBI')
    scored('LBI', status='truncated')
    db.session.commit()
    assert 'partial' in leaderboard.build_rows(['bluesky'], NOW)[0].marks


def test_segment_filtering(board):
    universe_row('LBBIG', cap='50000000000')
    universe_row('LBSML', cap='100000000')
    for ticker in ('LBBIG', 'LBSML'):
        scored(ticker)
    db.session.commit()

    assert [r.ticker for r in leaderboard.build_rows(['bluesky'], NOW,
                                                     segment='large')] == ['LBBIG']
    assert [r.ticker for r in leaderboard.build_rows(['bluesky'], NOW,
                                                     segment='micro')] == ['LBSML']


def test_a_ticker_missing_from_the_universe_still_ranks(board):
    """Mentions of a symbol we have no profile for are still mentions, and the
    Unknown segment is a first-class tab rather than a discard pile."""
    scored('LBZZ')
    db.session.commit()
    row = leaderboard.build_rows(['bluesky'], NOW)[0]
    assert row.ticker == 'LBZZ'
    assert row.segment == 'unknown'


def test_the_limit_is_respected(board):
    for index in range(8):
        ticker = 'LB%02d' % index
        universe_row(ticker)
        scored(ticker, z=float(index))
    db.session.commit()
    assert len(leaderboard.build_rows(['bluesky'], NOW, limit=3)) == 3
