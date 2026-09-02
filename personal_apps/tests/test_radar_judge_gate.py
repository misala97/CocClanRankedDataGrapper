"""Which tickers the model pass reads: watched ones, and reachable ones
outside the skipped segments. Real DB, future-dated seeds."""
import datetime as dt
import decimal

import pytest

from app import app as flask_app
from extensions import db
from features.radar import judge_gate
from models import RadarMention, RadarPost, RadarWatch, TickerUniverse
from conftest import _admin_id

NOW = dt.datetime(2027, 1, 1, 12, 0, 0)
AUTHORS = ['ann', 'bob', 'cy', 'dee', 'eve']


@pytest.fixture()
def clean():
    def wipe():
        RadarPost.query.filter(RadarPost.external_id.like('zzgate%')).delete(
            synchronize_session=False)
        TickerUniverse.query.filter(TickerUniverse.symbol.like('ZG%')).delete(
            synchronize_session=False)
        RadarWatch.query.filter(RadarWatch.ticker.like('ZG%')).delete(
            synchronize_session=False)
        db.session.commit()
    with flask_app.app_context():
        wipe()
        yield
        wipe()


def chatter(ticker, mentions, authors, minutes_ago=30):
    """`mentions` high-confidence mentions of `ticker` from `authors`
    distinct people, all `minutes_ago` before NOW."""
    when = NOW - dt.timedelta(minutes=minutes_ago)
    for i in range(mentions):
        post = RadarPost(source='bluesky', external_id=f'zzgate-{ticker}-{minutes_ago}-{i}',
                         channel='firehose', author=AUTHORS[i % authors],
                         created_utc=when, title=None, body=f'{ticker} chatter {i}',
                         first_seen=when, last_seen=when)
        db.session.add(post)
        db.session.flush()
        db.session.add(RadarMention(post_id=post.id, ticker=ticker, confidence='high',
                                    lexicon_sentiment=0.1))
    db.session.commit()


def profile(ticker, cap=None, is_etf=None):
    db.session.add(TickerUniverse(
        symbol=ticker, name=f'{ticker} Corp', exchange='Q',
        first_seen=dt.datetime(2020, 1, 1), is_etf=is_etf,
        market_cap=decimal.Decimal(cap) if cap else None))
    db.session.commit()


def gate():
    return judge_gate.judgeable_tickers(now=NOW)


# The gate reads every account's marks, and the dev DB carries real ones;
# counters are asserted as deltas against a baseline taken before seeding.
# Reachability is relative to NOW (2027), so real mentions contribute none.


def test_a_watched_ticker_is_judgeable_whatever_its_segment_or_volume(clean):
    with flask_app.app_context():
        baseline = gate()
        profile('ZGLARGE', cap='50000000000')
        db.session.add(RadarWatch(user_id=_admin_id(), ticker='ZGLARGE', created_at=NOW))
        db.session.commit()

        g = gate()

        assert 'ZGLARGE' in g.tickers
        assert g.watched == baseline.watched + 1


def test_large_and_fund_tickers_are_skipped_even_with_plenty_of_chatter(clean):
    with flask_app.app_context():
        baseline = gate()
        profile('ZGLARGE', cap='50000000000')
        profile('ZGFUND', cap='900000000', is_etf=True)
        chatter('ZGLARGE', 8, 4)
        chatter('ZGFUND', 8, 4)

        g = gate()

        assert 'ZGLARGE' not in g.tickers
        assert 'ZGFUND' not in g.tickers
        assert g.reachable == baseline.reachable + 2
        assert g.skipped_segment == baseline.skipped_segment + 2


def test_the_floor_needs_five_mentions_from_three_voices(clean):
    with flask_app.app_context():
        for ticker in ('ZGFEW', 'ZGVOICE', 'ZGOK'):
            profile(ticker, cap='4000000')
        chatter('ZGFEW', 4, 3)      # under on mentions
        chatter('ZGVOICE', 5, 2)    # under on voices
        chatter('ZGOK', 5, 3)       # at the floor

        g = gate()

        assert 'ZGOK' in g.tickers
        assert 'ZGFEW' not in g.tickers
        assert 'ZGVOICE' not in g.tickers


def test_a_mention_outside_the_window_does_not_count(clean):
    with flask_app.app_context():
        profile('ZGOLD', cap='4000000')
        chatter('ZGOLD', 4, 3, minutes_ago=30)
        chatter('ZGOLD', 1, 1, minutes_ago=25 * 60)   # 25h ago: outside 24h

        assert 'ZGOLD' not in gate().tickers


def test_a_ticker_without_a_universe_row_is_judged_when_reachable(clean):
    with flask_app.app_context():
        chatter('ZGNOCAP', 5, 3)

        assert 'ZGNOCAP' in gate().tickers


def test_the_kill_switch_disables_the_gate(clean, monkeypatch):
    with flask_app.app_context():
        monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)

        g = gate()

        assert g.enabled is False
        assert g.tickers == frozenset()
