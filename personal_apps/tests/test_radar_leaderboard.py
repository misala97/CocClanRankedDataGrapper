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

# Deliberately far from any window a live dev database holds data for. These
# tests assert on an exact list of LB* tickers, and the fixture can only clean
# up rows it created -- so an unrelated ticker sitting in the same window makes
# them fail on data rather than on behaviour. Found when a production snapshot
# was loaded locally for debugging and eighteen real tickers joined the board.
#
# Still a regular trading session (Thursday, 10:00 ET), which the price-status
# assertions depend on.
NOW = dt.datetime(2026, 1, 15, 15, 0, 0)


@pytest.fixture()
def board():
    # Clears every table these tests write to. A run that fails before its own
    # cleanup otherwise leaves rows that collide with the next one -- which is
    # exactly how this suite first broke.
    def wipe():
        from models import RadarMention, RadarPost
        RadarMention.query.filter(
            RadarMention.ticker.like('LB%')).delete(synchronize_session=False)
        RadarPost.query.filter(
            RadarPost.external_id.like('LB%')).delete(synchronize_session=False)
        for model in (RadarBucketSource, RadarQuote):
            model.query.filter(model.ticker.like('LB%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('LB%')).delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


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


_mention_seq = [0]


def _mention(ticker, author, minutes_ago, source='bluesky'):
    """A stored post and its mention, so the author is countable."""
    from models import RadarMention, RadarPost
    _mention_seq[0] += 1
    when = NOW - dt.timedelta(minutes=minutes_ago)
    post = RadarPost(source=source,
                     external_id='%s-%s-%d-%d' % (ticker, author, minutes_ago,
                                                  _mention_seq[0]),
                     channel='firehose', author=author, created_utc=when,
                     title=None, body='$%s' % ticker, score=0, num_comments=0,
                     url='https://example.invalid/', simhash=1,
                     first_seen=when, last_seen=when)
    db.session.add(post)
    db.session.flush()
    db.session.add(RadarMention(post_id=post.id, ticker=ticker,
                                confidence='high', lexicon_sentiment=0.0))


def test_authors_are_counted_across_the_window_not_per_bucket(board):
    """Buckets store a COUNT, so aggregating them can only take a maximum --
    and a maximum undercounts badly. Measured live: NVDA had 26 real authors
    against a bucket maximum of 2, and the floor needs three, so the maximum
    was rejecting nearly the whole board."""
    universe_row('LBW')
    # Four buckets, two distinct authors each, but eight distinct in total.
    for index in range(4):
        scored('LBW', minutes_ago=30 + index * 15, mentions=2, authors=2)
        _mention('LBW', 'author%d' % (index * 2), 30 + index * 15)
        _mention('LBW', 'author%d' % (index * 2 + 1), 30 + index * 15)
    db.session.commit()

    row = leaderboard.build_rows(['bluesky'], NOW)[0]
    assert row.authors == 8, 'window union, not the per-bucket maximum'


def test_the_bucket_maximum_is_the_fallback(board):
    """Once posts age out of retention the authors are gone, and the bucket
    count is all that remains. It undercounts, which can hide a ticker but can
    never invent breadth that was not there."""
    universe_row('LBX')
    scored('LBX', mentions=10, authors=7)
    db.session.commit()
    assert leaderboard.build_rows(['bluesky'], NOW)[0].authors == 7


def test_a_genuinely_concentrated_ticker_is_still_rejected(board):
    """The gate must keep working after the fix. Live data had PH at 14
    mentions from one author -- exactly what it exists to catch."""
    universe_row('LBY')
    scored('LBY', mentions=14, authors=1)
    for index in range(14):
        _mention('LBY', 'onlyvoice', 30)
    db.session.commit()
    assert leaderboard.build_rows(['bluesky'], NOW) == []


# Broadcast venues. A channel's admin is always one author, so the author gate
# can never be cleared there however loud a ticker gets; the independent unit
# is the channel instead.

def posted(ticker, external, source, channel, author, minutes_ago=20):
    """A post plus its mention, so author and channel counts are real.

    The bucket helpers above write COUNTS; these write the rows those counts
    are derived from, which is what the channel gate actually reads.
    """
    from models import RadarMention, RadarPost
    when = NOW - dt.timedelta(minutes=minutes_ago)
    row = RadarPost(source=source, external_id=external, channel=channel,
                    author=author, created_utc=when, body='x', score=0,
                    num_comments=0, simhash=abs(hash(external)) % 10 ** 9,
                    first_seen=when, last_seen=when)
    db.session.add(row)
    db.session.flush()
    db.session.add(RadarMention(post_id=row.id, ticker=ticker,
                                confidence='high', lexicon_sentiment=0.0))


def test_a_broadcast_only_ticker_reaches_the_board_on_two_channels(board, monkeypatch):
    """Before this, a Telegram-shaped source could never put a row up: one
    admin posts, every bucket has one author, and the author gate rejects it
    however loud the ticker gets.

    fourchan is borrowed as the broadcast source rather than inventing one,
    because a source not in config.SOURCES has no ingest path and could not
    have written these rows in the first place.
    """
    from features.radar import config

    monkeypatch.setitem(config.SOURCE_KIND, 'fourchan', 'broadcast')

    universe_row('LBB')
    scored('LBB', source='fourchan', mentions=8, authors=1)
    quoted('LBB', '100.00', '100.00')
    for n in range(8):
        posted('LBB', f'LBB{n}', 'fourchan',
               channel='chan-a' if n % 2 else 'chan-b', author='admin')
    db.session.commit()

    assert [r.ticker for r in leaderboard.build_rows(['fourchan'], NOW)] == ['LBB']


def test_one_channel_shouting_is_not_two_voices(board, monkeypatch):
    from features.radar import config

    monkeypatch.setitem(config.SOURCE_KIND, 'fourchan', 'broadcast')

    universe_row('LBC')
    scored('LBC', source='fourchan', mentions=8, authors=1)
    quoted('LBC', '100.00', '100.00')
    for n in range(8):
        posted('LBC', f'LBC{n}', 'fourchan', channel='chan-a', author='admin')
    db.session.commit()

    assert leaderboard.build_rows(['fourchan'], NOW) == []


def test_a_forum_ticker_is_unaffected_by_the_new_path(board):
    """The regression guard. Forum sources must behave exactly as before."""
    universe_row('LBD')
    scored('LBD', mentions=10, authors=6)
    quoted('LBD', '100.00', '100.00')
    db.session.commit()

    assert [r.ticker for r in leaderboard.build_rows(['bluesky'], NOW)] == ['LBD']
