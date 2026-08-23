"""Everything the board surface needs on top of the ranking.

`leaderboard` decides which tickers rank; `board` decides what has to be drawn
next to them -- the 24h shape, the three windows side by side, and how one-
sided the talk was. The rules being pinned here are all the same rule: an
absence is not a zero, and neither the series, the triplet nor the tone split
may quietly turn one into the other.
"""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import board
from features.radar.config import source_config_version
from models import (RadarBucketSource, RadarDailyClose, RadarMention,
                    RadarPost, RadarQuote, TickerUniverse)

# Deliberately outside any window a running dev database holds data for.
# `_covered_hours` asks "was ingest alive this hour" across ALL tickers, by
# design -- so a clock overlapping real rows would let unrelated data decide
# whether this suite's gaps read as gaps. Every radar suite shares one dev
# database (pytest does not spin up its own), which makes the choice of clock
# part of the isolation, not a detail.
NOW = dt.datetime(2026, 1, 15, 15, 0, 0)
PREFIX = 'BD'


@pytest.fixture()
def clean():
    """Clears every table these tests write to, before and after.

    Both ends, not just after: a run that failed before its own cleanup leaves
    rows that silently change the next run's answers.
    """
    def wipe():
        RadarMention.query.filter(
            RadarMention.ticker.like(f'{PREFIX}%')).delete(synchronize_session=False)
        RadarPost.query.filter(
            RadarPost.external_id.like(f'{PREFIX}%')).delete(synchronize_session=False)
        # RadarDailyClose included from the day it existed: its primary key
        # is (ticker, close_date), so a leaked row does not merely skew the
        # next test, it makes the next INSERT fail outright.
        for model in (RadarBucketSource, RadarQuote, RadarDailyClose):
            model.query.filter(model.ticker.like(f'{PREFIX}%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(
            TickerUniverse.symbol.like(f'{PREFIX}%')).delete(synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def universe(ticker, cap='50000000000'):
    db.session.add(TickerUniverse(
        symbol=ticker, name=f'{ticker} Corp', exchange='NYSE',
        first_seen=dt.datetime(2020, 1, 1), daily_sigma=0.02,
        market_cap=decimal.Decimal(cap) if cap else None))


def bucket(ticker, minutes_ago, source='bluesky', mentions=10, authors=6,
           expected=1.0, variance=2.0, z=5.0, status='ok'):
    db.session.add(RadarBucketSource(
        ticker=ticker, bucket_start=NOW - dt.timedelta(minutes=minutes_ago),
        source=source, mention_count=mentions, high_confidence_count=mentions,
        low_count=0, distinct_authors=authors, distinct_text_ratio=0.9,
        engagement_weighted_count=float(mentions), status=status,
        source_config_version=source_config_version(),
        expected=expected, variance=variance, mention_z=z, baseline_days=30))


def post(ticker, external, minutes_ago, sentiment, author=None,
         source='bluesky'):
    # A distinct author per post unless one is named: the eligibility floor
    # needs three, and reusing one name silently drops the row from the board
    # before any assertion about tone gets a chance to run.
    author = author or f'author-{external}'
    when = NOW - dt.timedelta(minutes=minutes_ago)
    row = RadarPost(source=source, external_id=external, channel='c',
                    author=author, created_utc=when, body='x', score=0,
                    num_comments=0, simhash=hash(external) % 10 ** 9,
                    first_seen=when, last_seen=when)
    db.session.add(row)
    db.session.flush()
    db.session.add(RadarMention(post_id=row.id, ticker=ticker,
                                confidence='high', lexicon_sentiment=sentiment))


def quote(ticker, minutes_ago, price):
    when = NOW - dt.timedelta(minutes=minutes_ago)
    db.session.add(RadarQuote(ticker=ticker, fetched_at=when, quote_ts=when,
                              price=decimal.Decimal(price),
                              prev_close=decimal.Decimal(price), volume=1000))


def only(built, ticker):
    return next(entry for entry in built.rows if entry.rank.ticker == ticker)


def at_hour(series, hours_ago):
    """The point for a whole hour, addressed the way the fixtures write it.

    Indexing from the end is a trap here: the last point is the hour NOW falls
    in, which is only partly elapsed and is frequently empty.
    """
    want = (NOW - dt.timedelta(hours=hours_ago)).replace(minute=0)
    return next(point for point in series if point.hour == want)


# ----------------------------------------------------------------- series ---

def test_an_hour_with_no_mentions_is_a_zero_when_ingest_was_running(clean):
    """A quiet hour is a real measurement of zero, and must draw as one."""
    universe(f'{PREFIX}A')
    universe(f'{PREFIX}B')
    bucket(f'{PREFIX}A', minutes_ago=30)
    # Another ticker was collected two hours back, so ingest demonstrably ran
    # in that hour -- our ticker simply had nothing said about it.
    bucket(f'{PREFIX}B', minutes_ago=90)
    db.session.commit()

    series = only(board.build(['bluesky'], NOW), f'{PREFIX}A').series

    assert at_hour(series, 1).count == 10
    assert at_hour(series, 2).count == 0


def test_an_hour_nothing_was_collected_in_is_unmeasured_not_zero(clean):
    """The rule the whole feature turns on. Drawing a floor across a gap in
    ingest invents a measurement, and the next spike then looks bigger than it
    was."""
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    db.session.commit()

    series = only(board.build(['bluesky'], NOW), f'{PREFIX}A').series
    gaps = [point for point in series if point.count is None]

    assert at_hour(series, 1).count == 10
    # Every other hour of the 25 the window spans, the hour NOW is in included.
    assert len(gaps) == 24


def test_a_source_that_was_down_does_not_make_the_hour_look_collected(clean):
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    bucket(f'{PREFIX}A', minutes_ago=150, status='missing', mentions=0)
    db.session.commit()

    series = only(board.build(['bluesky'], NOW), f'{PREFIX}A').series
    two_ago = next(p for p in series
                   if p.hour == (NOW - dt.timedelta(hours=2)).replace(minute=0))

    assert two_ago.count is None


def test_the_series_pools_the_selected_sources_only(clean):
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30, source='bluesky', mentions=6)
    bucket(f'{PREFIX}A', minutes_ago=30, source='fourchan', mentions=4)
    db.session.commit()

    both = only(board.build(['bluesky', 'fourchan'], NOW), f'{PREFIX}A')
    one = only(board.build(['bluesky'], NOW), f'{PREFIX}A')

    assert at_hour(both.series, 1).count == 10
    assert at_hour(one.series, 1).count == 6


# ---------------------------------------------------------------- triplet ---

def test_the_triplet_sums_components_rather_than_averaging_z(clean):
    """A mean of z-scores is not a z-score (spec 6.2). Two buckets each at
    z=5 pool to a higher z, not to 5."""
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=10, mentions=10, expected=1.0, variance=2.0)
    bucket(f'{PREFIX}A', minutes_ago=90, mentions=10, expected=1.0, variance=2.0)
    db.session.commit()

    triplet = only(board.build(['bluesky'], NOW), f'{PREFIX}A').triplet

    # 1h sees one bucket, 4h sees both. Averaging the two z-scores would give
    # 6.36 for the wider window; summing the components gives 9.
    assert triplet[1] == pytest.approx((10 - 1) / 2 ** 0.5)
    assert triplet[4] == pytest.approx((20 - 2) / 4 ** 0.5)
    assert triplet[4] > triplet[1]


def test_a_window_with_no_buckets_scores_none_not_zero(clean):
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=400)
    db.session.commit()

    triplet = only(board.build(['bluesky'], NOW, window_hours=24), f'{PREFIX}A').triplet

    assert triplet[1] is None
    assert triplet[4] is None
    assert triplet[24] is not None


def test_the_triplet_is_the_same_three_windows_whatever_is_selected(clean):
    """The point of showing all three is that building and fading can be told
    apart without changing the control and remembering."""
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    db.session.commit()

    for window in (1, 4, 24):
        built = board.build(['bluesky'], NOW, window_hours=window)
        assert set(only(built, f'{PREFIX}A').triplet) == {1, 4, 24}


# ------------------------------------------------------------------- tone ---

def test_tone_counts_neutral_separately_rather_than_folding_it_in(clean):
    """Lexicon sentiment is 0.0 both for balanced and for "no sentiment word
    matched", and the second dominates. A single "% bullish" over that is
    noise wearing a percentage sign."""
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    post(f'{PREFIX}A', f'{PREFIX}1', 30, 0.6)
    post(f'{PREFIX}A', f'{PREFIX}2', 30, -0.4)
    post(f'{PREFIX}A', f'{PREFIX}3', 30, 0.0)
    post(f'{PREFIX}A', f'{PREFIX}4', 30, 0.0)
    post(f'{PREFIX}A', f'{PREFIX}5', 30, 0.0)
    db.session.commit()

    tone = only(board.build(['bluesky'], NOW), f'{PREFIX}A').tone

    assert (tone.bullish, tone.bearish, tone.neutral) == (1, 1, 3)
    assert tone.scored == 2


def test_tone_ignores_posts_from_a_source_that_is_switched_off(clean):
    universe(f'{PREFIX}A')
    bucket(f'{PREFIX}A', minutes_ago=30)
    for index in range(3):
        post(f'{PREFIX}A', f'{PREFIX}b{index}', 30, 0.6, source='bluesky')
    post(f'{PREFIX}A', f'{PREFIX}f0', 30, 0.6, source='fourchan')
    db.session.commit()

    tone = only(board.build(['bluesky'], NOW), f'{PREFIX}A').tone

    assert tone.bullish == 3


# --------------------------------------------------------------- assembly ---

def test_segment_counts_are_taken_before_the_segment_filter(clean):
    """They label the filter's own buttons. Counted after it, every button
    would report the selected segment's size."""
    universe(f'{PREFIX}A', cap='50000000000')      # large
    universe(f'{PREFIX}B', cap='1000000000')       # mid
    bucket(f'{PREFIX}A', minutes_ago=30)
    bucket(f'{PREFIX}B', minutes_ago=30)
    db.session.commit()

    built = board.build(['bluesky'], NOW, segment='mid')

    assert [entry.rank.ticker for entry in built.rows] == [f'{PREFIX}B']
    assert built.segment_counts['large'] >= 1
    assert built.segment_counts['mid'] >= 1
    assert built.segment_counts['all'] >= 2


# The lead cards' intraday quote series is gone. They now draw the same
# span-switched chart the scan rows do, so the payload field, its per-row quote
# query and the geometry that read it all lost their last consumer.


# The chart moved to the detail panel on 2026-08-23, and its tests with
# it -- see test_radar_detail.py. The board no longer ships one.

# ----------------------------------------------------------------- venues ---
#
# Breadth as a filter, not as a score. What more than one venue is talking
# about at the same time is a different question from what is loudest.

def test_the_venue_filter_keeps_only_corroborated_rows(clean):
    universe(f'{PREFIX}A')
    universe(f'{PREFIX}B')
    bucket(f'{PREFIX}A', minutes_ago=30, source='bluesky')
    bucket(f'{PREFIX}B', minutes_ago=30, source='bluesky')
    bucket(f'{PREFIX}B', minutes_ago=30, source='fourchan')
    db.session.commit()

    built = board.build(['bluesky', 'fourchan'], NOW, min_venues=2)

    assert [e.rank.ticker for e in built.rows] == [f'{PREFIX}B']


def test_venue_counts_are_taken_before_the_venue_filter(clean):
    """Same rule the segment counts follow: the counts label the control, so
    computing them after the filter would report the filtered size in both
    slots."""
    universe(f'{PREFIX}A')
    universe(f'{PREFIX}B')
    bucket(f'{PREFIX}A', minutes_ago=30, source='bluesky')
    bucket(f'{PREFIX}B', minutes_ago=30, source='bluesky')
    bucket(f'{PREFIX}B', minutes_ago=30, source='fourchan')
    db.session.commit()

    built = board.build(['bluesky', 'fourchan'], NOW, min_venues=2)

    assert built.venue_counts['any'] == 2
    assert built.venue_counts['multi'] == 1


# ---------------------------------------------------------------- segments ---

def test_small_unions_the_three_segments_below_mid(clean):
    """The tool is for penny stocks and unknowns. `Small` is what that means
    in the segment vocabulary: anything not large and not mid."""
    universe(f'{PREFIX}A', cap='50000000000')      # large
    universe(f'{PREFIX}B', cap='100000000')        # micro
    universe(f'{PREFIX}C', cap=None)               # unknown
    for suffix in 'ABC':
        bucket(f'{PREFIX}{suffix}', minutes_ago=30)
    db.session.commit()

    built = board.build(['bluesky'], NOW, segment='small')
    got = {entry.rank.ticker for entry in built.rows}

    assert got == {f'{PREFIX}B', f'{PREFIX}C'}


def test_a_row_in_small_still_reports_its_own_segment(clean):
    """`Small` is a filter, not a sixth segment. A micro-cap is still micro,
    or the segment counts would stop summing to the total."""
    universe(f'{PREFIX}B', cap='100000000')
    bucket(f'{PREFIX}B', minutes_ago=30)
    db.session.commit()

    built = board.build(['bluesky'], NOW, segment='small')

    assert built.rows[0].rank.segment == 'micro'
