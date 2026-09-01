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
from models import (RadarBucketSource, RadarDailyClose, RadarInstrument,
                    RadarQuote, TickerUniverse)
from features.radar import leaderboard
from features.radar.config import source_config_version
from test_radar_journal import _row, _ALL_OK, clean_buckets, clean_events  # noqa: F401

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
        from models import RadarMention, RadarMentionEvent, RadarPost
        RadarMention.query.filter(
            RadarMention.ticker.like('LB%')).delete(synchronize_session=False)
        RadarPost.query.filter(
            RadarPost.external_id.like('LB%')).delete(synchronize_session=False)
        # Since Task 3b, _distinct_authors/_distinct_channels read the journal
        # instead of radar_mentions -- the helpers below write matching rows
        # here too, so this table needs the same LB* cleanup as the others.
        RadarMentionEvent.query.filter(
            RadarMentionEvent.ticker.like('LB%')).delete(synchronize_session=False)
        for model in (RadarBucketSource, RadarDailyClose, RadarInstrument, RadarQuote):
            model.query.filter(model.ticker.like('LB%')).delete(
                synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('LB%')).delete(
            synchronize_session=False)
        db.session.commit()

    with flask_app.app_context():
        wipe()
        yield
        wipe()


def build_rows(*args, **kwargs):
    """Rows only.

    leaderboard.build_rows returns a Ranking since 2026-08-23 -- rows plus
    an account of what the floor excluded. The tests below predate that and
    are about ordering and row content, so they take the rows and ignore the
    account. Tests that are ABOUT the account call the real API.
    """
    return leaderboard.build_rows(*args, **kwargs).rows


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

    rows = build_rows(['bluesky'], NOW)
    assert [r.ticker for r in rows] == ['LBA']
    assert rows[0].name == 'Test Corp'
    assert rows[0].mentions == 10


def test_germany_row_uses_a_marked_us_quote_fallback(board):
    """A missing Xetra instrument does not disappear or pretend to be EUR."""
    universe_row('LBDE')
    scored('LBDE')
    quoted('LBDE', '100.00', '98.00')
    db.session.commit()

    row = build_rows(['bluesky'], NOW, market='de')[0]

    assert row.quote.market == 'us'
    assert row.quote.currency == 'USD'
    assert row.quote.is_fallback is True
    assert row.quote.session == 'regular'


def test_eod_german_quote_cannot_produce_divergence(board):
    """A retained prior-day Xetra print remains readable but never looks live."""
    ticker = 'LBEOD'
    universe_row(ticker)
    scored(ticker)
    db.session.add(RadarInstrument(
        ticker=ticker, market='de', venue='Xetra', mic='XETR',
        provider_symbol='LBEOD', currency='EUR', is_primary=True,
        mapping_status='mapped', mapped_at=NOW))
    db.session.add(RadarQuote(
        ticker=ticker, market='de', mic='XETR', currency='EUR',
        provider_symbol='LBEOD', fetched_at=NOW - dt.timedelta(minutes=5),
        quote_ts=NOW - dt.timedelta(days=1), price=decimal.Decimal('100'),
        prev_close=decimal.Decimal('98'), volume=1000))
    db.session.commit()

    row = build_rows(['bluesky'], NOW, market='de')[0]

    assert row.quote.quality == 'eod'
    assert row.divergence is None


def test_german_quote_does_not_use_the_us_cached_sigma(board):
    """No Xetra close history means no German volatility opinion."""
    ticker = 'LBDESIG'
    universe_row(ticker)
    scored(ticker)
    profile = TickerUniverse.query.filter_by(symbol=ticker).one()
    profile.daily_sigma = 0.01
    db.session.add(RadarInstrument(
        ticker=ticker, market='de', venue='Xetra', mic='XETR',
        provider_symbol=ticker, currency='EUR', is_primary=True,
        mapping_status='mapped', mapped_at=NOW))
    for minutes, price in ((30, '100'), (5, '101')):
        when = NOW - dt.timedelta(minutes=minutes)
        db.session.add(RadarQuote(
            ticker=ticker, market='de', mic='XETR', currency='EUR',
            provider_symbol=ticker, fetched_at=when, quote_ts=when,
            price=decimal.Decimal(price), prev_close=decimal.Decimal('100')))
    db.session.commit()

    row = build_rows(['bluesky'], NOW, market='de')[0]

    assert row.quote.market == 'de'
    assert row.price_move == decimal.Decimal('0.01')
    assert row.divergence is None


def test_an_ineligible_ticker_is_excluded_not_ranked_low(board):
    """Below the floor there is no signal to rank. Showing it at the bottom
    would imply it was measured and found wanting, when it was never
    measurable."""
    universe_row('LBB')
    scored('LBB', mentions=2, authors=1)
    db.session.commit()
    assert build_rows(['bluesky'], NOW) == []


def test_ranking_is_by_divergence(board):
    """Loud and unmoved outranks equally loud and already up."""
    universe_row('LBUP')
    universe_row('LBFLAT')
    for ticker in ('LBUP', 'LBFLAT'):
        scored(ticker)
    quoted('LBUP', '112.00', '100.00')     # ran hard
    quoted('LBFLAT', '100.20', '100.00')   # barely moved
    db.session.commit()

    rows = build_rows(['bluesky'], NOW)
    assert [r.ticker for r in rows] == ['LBFLAT', 'LBUP']


def test_only_the_selected_sources_are_pooled(board):
    """The selector is a read-time filter over stored components."""
    universe_row('LBC')
    scored('LBC', source='bluesky', mentions=6, z=3.0)
    scored('LBC', source='fourchan', mentions=6, z=3.0)
    db.session.commit()

    both = build_rows(['bluesky', 'fourchan'], NOW)[0]
    one = build_rows(['bluesky'], NOW)[0]
    assert both.mentions == 12
    assert one.mentions == 6
    assert both.mention_z > one.mention_z


def test_a_row_records_which_sources_contributed(board):
    universe_row('LBD')
    scored('LBD', source='bluesky')
    scored('LBD', source='fourchan')
    db.session.commit()
    row = build_rows(['bluesky', 'fourchan'], NOW)[0]
    assert set(row.sources) == {'bluesky', 'fourchan'}


def test_a_single_source_row_is_marked(board):
    """The same divergence backed by two independent sources is stronger
    evidence than one, and the row has to say which it is."""
    universe_row('LBE')
    scored('LBE', source='bluesky')
    db.session.commit()
    assert 'single-source' in build_rows(['bluesky', 'fourchan'],
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

    row = build_rows(['bluesky'], NOW)[0]
    assert row.divergence is None
    assert 'no-print' in row.marks


def test_a_ticker_with_no_quote_still_appears_without_divergence(board):
    """The chatter is real even when we have no price for it. Dropping the row
    would hide a genuine signal; inventing a divergence would fabricate one."""
    universe_row('LBG')
    scored('LBG')
    db.session.commit()
    row = build_rows(['bluesky'], NOW)[0]
    assert row.divergence is None
    assert row.price is None


def test_a_thin_baseline_is_marked_provisional(board):
    universe_row('LBH')
    scored('LBH', baseline_days=3)
    db.session.commit()
    row = build_rows(['bluesky'], NOW)[0]
    assert 'provisional' in row.marks
    # A ticker with genuine multi-day history is not "warming up" -- that
    # word is reserved for a baseline thinner than a day.
    assert 'warming-up' not in row.marks


def test_a_baseline_under_a_day_is_marked_warming_up_not_provisional(board):
    """Two different facts wear the same badge otherwise: a NEW ticker has
    thin history of its own, but a config-version change gives EVERY ticker
    on the board under a day of history at once. Production: baseline_days
    truncated to 0 on 147,228 of 147,429 scored Bluesky rows, which fired
    `provisional` on the whole board -- a mark that fires on every row is not
    a mark."""
    universe_row('LBW')
    scored('LBW', baseline_days=0.5)
    db.session.commit()
    row = build_rows(['bluesky'], NOW)[0]
    assert 'warming-up' in row.marks
    assert 'provisional' not in row.marks


def test_a_truncated_source_is_marked_partial(board):
    universe_row('LBI')
    scored('LBI', status='truncated')
    db.session.commit()
    assert 'partial' in build_rows(['bluesky'], NOW)[0].marks


def test_segment_filtering(board):
    universe_row('LBBIG', cap='50000000000')
    universe_row('LBSML', cap='100000000')
    for ticker in ('LBBIG', 'LBSML'):
        scored(ticker)
    db.session.commit()

    assert [r.ticker for r in build_rows(['bluesky'], NOW,
                                                     segments=['large'])] == ['LBBIG']
    assert [r.ticker for r in build_rows(['bluesky'], NOW,
                                                     segments=['micro'])] == ['LBSML']


def test_a_ticker_missing_from_the_universe_still_ranks(board):
    """Mentions of a symbol we have no profile for are still mentions, and the
    Unknown segment is a first-class tab rather than a discard pile."""
    scored('LBZZ')
    db.session.commit()
    row = build_rows(['bluesky'], NOW)[0]
    assert row.ticker == 'LBZZ'
    assert row.segment == 'unknown'


def test_the_limit_is_respected(board):
    for index in range(8):
        ticker = 'LB%02d' % index
        universe_row(ticker)
        scored(ticker, z=float(index))
    db.session.commit()
    assert len(build_rows(['bluesky'], NOW, limit=3)) == 3


_mention_seq = [0]


def _mention(ticker, author, minutes_ago, source='bluesky'):
    """A stored post and its mention, so the author is countable.

    Also writes the journal row _distinct_authors reads since Task 3b. A real
    `high` mention still lands in radar_mentions too -- only the promoted
    `medium` and post-was-all-low cases are journal-only -- so writing both
    here mirrors production rather than special-casing the test.
    """
    from models import RadarMention, RadarMentionEvent, RadarPost
    from features.radar import buckets
    _mention_seq[0] += 1
    when = NOW - dt.timedelta(minutes=minutes_ago)
    external_id = '%s-%s-%d-%d' % (ticker, author, minutes_ago, _mention_seq[0])
    post = RadarPost(source=source, external_id=external_id,
                     channel='firehose', author=author, created_utc=when,
                     title=None, body='$%s' % ticker, score=0, num_comments=0,
                     url='https://example.invalid/', simhash=1,
                     first_seen=when, last_seen=when)
    db.session.add(post)
    db.session.flush()
    db.session.add(RadarMention(post_id=post.id, ticker=ticker,
                                confidence='high', lexicon_sentiment=0.0))
    db.session.add(RadarMentionEvent(
        source=source, external_id=external_id, ticker=ticker,
        channel='firehose', created_utc=when,
        bucket_start=buckets.bucket_start_for(when), author=author,
        simhash=_mention_seq[0], confidence='high', sentiment=None,
        engagement=0.0))


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

    row = build_rows(['bluesky'], NOW)[0]
    assert row.authors == 8, 'window union, not the per-bucket maximum'


def test_the_bucket_maximum_is_the_fallback(board):
    """Once posts age out of retention the authors are gone, and the bucket
    count is all that remains. It undercounts, which can hide a ticker but can
    never invent breadth that was not there."""
    universe_row('LBX')
    scored('LBX', mentions=10, authors=7)
    db.session.commit()
    assert build_rows(['bluesky'], NOW)[0].authors == 7


def test_the_pre_split_reddit_voices_still_count(board):
    """The journal's voice count is raw, so it sees the older root name.

    Distinct authors are people, not baselines: the person who posted under
    the pre-split `reddit` name and the person who posted under
    `reddit:wallstreetbets` are the same population. Dropping the older half
    would undercount breadth for every ticker discussed before 2026-08-26 and
    could push it below the eligibility floor -- the board reading thinner
    than the evidence it holds.
    """
    from features.radar import journal

    universe_row('LBH')
    scored('LBH', source='reddit:wallstreetbets', mentions=4, authors=2)
    _mention('LBH', 'newvoice1', 30, source='reddit:wallstreetbets')
    _mention('LBH', 'newvoice2', 30, source='reddit:wallstreetbets')
    _mention('LBH', 'oldvoice1', 45, source='reddit')
    _mention('LBH', 'oldvoice2', 45, source='reddit')
    db.session.commit()

    voices = journal.distinct_voices(
        ['LBH'], ['reddit'], NOW - dt.timedelta(hours=4), NOW, 'author')

    assert voices['LBH'] == 4


def test_a_genuinely_concentrated_ticker_is_still_rejected(board):
    """The gate must keep working after the fix. Live data had PH at 14
    mentions from one author -- exactly what it exists to catch."""
    universe_row('LBY')
    scored('LBY', mentions=14, authors=1)
    for index in range(14):
        _mention('LBY', 'onlyvoice', 30)
    db.session.commit()
    assert build_rows(['bluesky'], NOW) == []


# Broadcast venues. A channel's admin is always one author, so the author gate
# can never be cleared there however loud a ticker gets; the independent unit
# is the channel instead.

def posted(ticker, external, source, channel, author, minutes_ago=20):
    """A post plus its mention, so author and channel counts are real.

    The bucket helpers above write COUNTS; these write the rows those counts
    are derived from, which is what the channel gate actually reads -- the
    mention journal since Task 3b, alongside radar_mentions for the same
    reason _mention above writes both.
    """
    from models import RadarMention, RadarMentionEvent, RadarPost
    from features.radar import buckets
    when = NOW - dt.timedelta(minutes=minutes_ago)
    simhash = abs(hash(external)) % 10 ** 9
    row = RadarPost(source=source, external_id=external, channel=channel,
                    author=author, created_utc=when, body='x', score=0,
                    num_comments=0, simhash=simhash,
                    first_seen=when, last_seen=when)
    db.session.add(row)
    db.session.flush()
    db.session.add(RadarMention(post_id=row.id, ticker=ticker,
                                confidence='high', lexicon_sentiment=0.0))
    db.session.add(RadarMentionEvent(
        source=source, external_id=external, ticker=ticker, channel=channel,
        created_utc=when, bucket_start=buckets.bucket_start_for(when),
        author=author, simhash=simhash, confidence='high', sentiment=None,
        engagement=0.0))


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

    assert [r.ticker for r in build_rows(['fourchan'], NOW)] == ['LBB']


def test_one_channel_shouting_is_not_two_voices(board, monkeypatch):
    from features.radar import config

    monkeypatch.setitem(config.SOURCE_KIND, 'fourchan', 'broadcast')

    universe_row('LBC')
    scored('LBC', source='fourchan', mentions=8, authors=1)
    quoted('LBC', '100.00', '100.00')
    for n in range(8):
        posted('LBC', f'LBC{n}', 'fourchan', channel='chan-a', author='admin')
    db.session.commit()

    assert build_rows(['fourchan'], NOW) == []


def test_a_forum_ticker_is_unaffected_by_the_new_path(board):
    """The regression guard. Forum sources must behave exactly as before."""
    universe_row('LBD')
    scored('LBD', mentions=10, authors=6)
    quoted('LBD', '100.00', '100.00')
    db.session.commit()

    assert [r.ticker for r in build_rows(['bluesky'], NOW)] == ['LBD']


# What the floor left out, added 2026-08-23. Without it a two-row board and a
# stopped ingest render identically.

def test_a_ticker_below_the_voice_gate_is_counted_not_just_dropped(board):
    universe_row('LBQUIET')
    scored('LBQUIET', authors=1)
    db.session.commit()

    ranking = leaderboard.build_rows(['bluesky'], NOW)

    assert ranking.rows == []
    assert ranking.excluded['too_few_voices'] == 1


def test_a_ticker_that_clears_the_floor_is_not_counted_as_excluded(board):
    universe_row('LBA')
    scored('LBA')
    db.session.commit()

    ranking = leaderboard.build_rows(['bluesky'], NOW)

    assert [r.ticker for r in ranking.rows] == ['LBA']
    assert sum(ranking.excluded.values()) == 0


def test_the_breadth_filter_is_counted_apart_from_the_floor(board):
    """`one venue only` is the reader's own filter doing what they asked, not
    the data being too thin to measure. Merging them would tell the reader the
    data was worse than it is."""
    universe_row('LBA')
    scored('LBA')
    db.session.commit()

    ranking = leaderboard.build_rows(['bluesky'], NOW, min_venues=2)

    assert ranking.rows == []
    assert ranking.excluded['one_venue'] == 1
    assert ranking.excluded.get('too_few_voices', 0) == 0


def test_repeated_text_is_named_as_such(board):
    """Fifty voices pasting one message defeat the voice gate completely, and
    "too few voices" would be the wrong account of why it was dropped."""
    universe_row('LBSPAM')
    scored('LBSPAM', authors=40, text_ratio=0.01)
    db.session.commit()

    ranking = leaderboard.build_rows(['bluesky'], NOW)

    assert ranking.rows == []
    assert ranking.excluded['repeated_text'] == 1


def test_a_thin_ticker_is_reported_by_how_far_it_got(board):
    """A later gate means the earlier ones passed, so the furthest failure is
    the most informative description. Two mentions is a volume problem, and
    calling it a voice problem would send the reader after the wrong fix."""
    universe_row('LBTINY')
    scored('LBTINY', mentions=2, authors=1)
    db.session.commit()

    ranking = leaderboard.build_rows(['bluesky'], NOW)

    assert ranking.excluded['too_few_mentions'] == 1
    assert 'too_few_voices' not in ranking.excluded


def test_the_reason_is_the_furthest_gate_any_kind_reached():
    """Only reachable with a broadcast source configured, which there is not
    today -- so it is unit-tested directly rather than left to rot untested
    until Telegram lands.

    A ticker glanced at by one channel and discussed by forty forum authors
    who all pasted the same text failed on wording, not on breadth. Reporting
    the channel's failure would send the reader after the wrong fix.
    """
    from features.radar.scoring import Contribution

    reason = leaderboard._rejection({
        'broadcast': Contribution(mentions=1, voices=1, text_ratio=1.0),
        'forum': Contribution(mentions=40, voices=40, text_ratio=0.01),
    })

    assert reason == 'repeated_text'


def test_a_kind_that_passes_clears_the_whole_ticker():
    """Eligibility is a union across kinds, so one passing kind means no
    rejection at all -- not a rejection described by the other one."""
    from features.radar.scoring import Contribution

    assert leaderboard._rejection({
        'broadcast': Contribution(mentions=1, voices=1, text_ratio=1.0),
        'forum': Contribution(mentions=40, voices=40, text_ratio=0.9),
    }) is None


def test_a_promoted_mention_counts_towards_the_author_floor(clean_buckets,
                                                            clean_events):
    """The floor gated on a count that could not see half the mentions.

    `medium` is awarded at rollup and never written to radar_mentions -- zero
    such rows exist in production -- and a post whose tickers were all `low` is
    never stored at all. So bucket.mention_count counted the promoted mentions
    and the author query could not, and the eligibility floor judged a ticker
    on the smaller number (audit 2026-08-26).
    """
    import datetime as dt

    from features.radar import buckets, journal

    start = {dt.datetime(2026, 4, 15, 14, 0, 0)}
    buckets.roll_up([
        _row(external_id='zz-h', author='u1', simhash=1, confidence='high'),
        _row(external_id='zz-l', author='u2', simhash=2, confidence='low',
             minute=7),
    ], _ALL_OK, start)

    voices = journal.distinct_voices(
        ['ZZA'], ['bluesky'], dt.datetime(2026, 4, 15, 13, 0, 0),
        dt.datetime(2026, 4, 15, 15, 0, 0), 'author')
    # u2's bare mention was vouched for by u1's cashtag, so it is scored --
    # and its author is one of the ticker's independent voices.
    assert voices['ZZA'] == 2


def test_voices_are_counted_only_for_tickers_that_clear_the_mention_floor(board, monkeypatch):
    """Pass one asked the journal for distinct authors AND channels of every
    ticker with a scored bucket -- thousands on the 24h board, two queries,
    3.3s measured 2026-09-01 -- when a ticker under MIN_MENTIONS can never
    be eligible whatever its voices say. One query, for the ones it can
    matter to."""
    universe_row('LBQ')
    scored('LBQ', mentions=10)
    scored('LBQT', mentions=2)
    quoted('LBQ', '100.00', '100.00')
    db.session.commit()

    asked = []
    real = leaderboard.journal.distinct_voice_counts

    def spy(tickers, sources, since, now):
        asked.append(sorted(tickers))
        return real(tickers, sources, since, now)
    monkeypatch.setattr(leaderboard.journal, 'distinct_voice_counts', spy)

    ranking = leaderboard.build_rows(['bluesky'], NOW)

    assert len(asked) == 1
    assert 'LBQ' in asked[0]
    assert 'LBQT' not in asked[0]
    # Still accounted for, on the gate it actually failed.
    assert ranking.excluded.get('too_few_mentions') == 1


def test_sigma_history_is_read_once_per_day(monkeypatch):
    """_quote_sigmas fetched 780 closes per survivor on every build -- 31k
    rows and 600ms on the 24h board -- for a figure that changes once a day
    when a close arrives."""
    import types
    calls = []
    monkeypatch.setattr(leaderboard.history, 'closes_for',
                        lambda tickers, **kw: (calls.append(list(tickers)), {})[1])
    views = {'LBS': types.SimpleNamespace(market='us', mic='XNAS')}
    leaderboard.sigma_cache.clear()

    leaderboard._quote_sigmas(views, dt.date(2026, 1, 15))
    leaderboard._quote_sigmas(views, dt.date(2026, 1, 15))
    assert len(calls) == 1

    leaderboard._quote_sigmas(views, dt.date(2026, 1, 16))
    assert len(calls) == 2
