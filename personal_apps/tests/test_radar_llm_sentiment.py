# personal_apps/tests/test_radar_llm_sentiment.py
"""The scheduled v2 judgment pass, end to end against the dev database.

Parse-level and storage-level behavior lives in test_radar_sentiment_v2;
this file covers the pass: what pending() selects, what run_pass writes
and books, and how partial failure degrades. Fixtures are future-dated
because these suites run against the real local development database
with no transactional isolation.
"""
import datetime as dt
import json

import pytest

from app import app as flask_app
from extensions import db
from features.radar import llm_sentiment
from models import RadarLlmSpend, RadarMention, RadarPost

NOW = dt.datetime(2027, 1, 1, 12, 0, 0)


class FakeResponse:
    def __init__(self, text, stop_reason='end_turn', usage=None):
        self.content = [type('Block', (), {'type': 'text', 'text': text})()]
        self.stop_reason = stop_reason
        self.usage = usage


class FakeMessages:
    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeClient:
    def __init__(self, answers):
        self.messages = FakeMessages(answers)


def entry(n, attitude='positive', relevance='relevant',
          origin='human_chatter', move='up', confidence='high'):
    return {'n': n, 'relevance': relevance, 'content_origin': origin,
            'attitude': attitude, 'expected_move': move,
            'confidence': confidence}


def answer(entries, usage=None):
    return FakeResponse(json.dumps({'verdicts': entries}), usage=usage)


def usage_of(input_tokens, output_tokens):
    return type('U', (), {'input_tokens': input_tokens,
                          'output_tokens': output_tokens})()


@pytest.fixture()
def clean_posts():
    with flask_app.app_context():
        RadarPost.query.filter(RadarPost.external_id.like('zztest%')).delete(
            synchronize_session=False)
        db.session.commit()
        yield
        RadarPost.query.filter(RadarPost.external_id.like('zztest%')).delete(
            synchronize_session=False)
        db.session.commit()


@pytest.fixture(autouse=True)
def gate_off(monkeypatch):
    """The pass tests below are about the pass, not the gate: a lone seeded
    mention must still be judged. The gate tests re-enable it explicitly."""
    from features.radar import judge_gate
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)


def make_post(external_id, ticker='ZZA', confidence='high',
              llm=None, body='ZZA ripping', judged_at=None, when=NOW):
    post = RadarPost(source='bluesky', external_id=external_id,
                     channel='firehose', author='someone', created_utc=when,
                     title=None, body=body, first_seen=when, last_seen=when)
    db.session.add(post)
    db.session.flush()
    mention = RadarMention(post_id=post.id, ticker=ticker,
                           confidence=confidence, lexicon_sentiment=0.25,
                           llm_sentiment=llm, sentiment_judged_at=judged_at)
    db.session.add(mention)
    db.session.commit()
    return mention.id


def ids_pending(limit=50):
    return {mention.id for mention, _post in llm_sentiment.pending(limit)}


def test_only_high_confidence_mentions_are_judged(clean_posts):
    """`low` is never scored, so paying to read it buys nothing the board
    can use. `medium` is awarded in memory at rollup and never stored."""
    with flask_app.app_context():
        high = make_post('zztest-high', confidence='high')
        low = make_post('zztest-low', confidence='low')

        waiting = ids_pending()

        assert high in waiting
        assert low not in waiting


def test_an_already_judged_mention_is_not_repicked(clean_posts):
    with flask_app.app_context():
        judged = make_post('zztest-judged', judged_at=NOW)
        assert judged not in ids_pending()


def test_run_pass_judges_pending_and_books_spend(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztest-pass')
        client = FakeClient([answer([entry(1)], usage=usage_of(120, 30))])
        spent_before = (db.session.query(RadarLlmSpend).get(
            (dt.date.today(), llm_sentiment.PRIMARY_MODEL)))
        before_tokens = spent_before.input_tokens if spent_before else 0

        judged = llm_sentiment.run_pass(client=client, limit=5)

        assert judged == 1
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'positive'
        assert m.llm_sentiment == 'bullish'
        assert client.messages.requests[0]['model'] == \
            llm_sentiment.PRIMARY_MODEL
        spent = db.session.query(RadarLlmSpend).get(
            (dt.date.today(), llm_sentiment.PRIMARY_MODEL))
        assert spent.input_tokens >= before_tokens + 120


def test_one_failed_batch_leaves_its_mentions_retryable(clean_posts):
    with flask_app.app_context():
        ids = [make_post('zztest-batch-%02d' % i)
               for i in range(llm_sentiment.BATCH_SIZE + 1)]
        # Newest-first ordering ties on created_utc; whichever batch fails,
        # its members must stay pending while the other batch is written.
        ok = answer([entry(n) for n in range(1, llm_sentiment.BATCH_SIZE + 1)])
        import anthropic
        boom = anthropic.APIConnectionError(request=None)
        client = FakeClient([ok, boom])

        judged = llm_sentiment.run_pass(client=client,
                                        limit=llm_sentiment.BATCH_SIZE + 1)

        assert judged == llm_sentiment.BATCH_SIZE
        # The dev database carries its own real pending backlog; only the
        # fixture rows are this test's business.
        still_waiting = set(ids) & ids_pending(limit=100)
        assert len(still_waiting) == 1


def test_a_duplicated_item_number_keeps_only_one_answer(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztest-dup')
        client = FakeClient([answer([entry(1, attitude='positive'),
                                     entry(1, attitude='negative',
                                           move='down')])])
        judged = llm_sentiment.run_pass(client=client, limit=5)
        assert judged == 1
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude in ('positive', 'negative')


def test_every_enum_value_fits_its_column():
    m = RadarMention.__table__.c
    checks = [
        (llm_sentiment.RELEVANCE, m.sentiment_relevance),
        (llm_sentiment.CONTENT_ORIGIN, m.sentiment_content_origin),
        (llm_sentiment.ATTITUDE, m.sentiment_attitude),
        (llm_sentiment.EXPECTED_MOVE, m.sentiment_expected_move),
        (llm_sentiment.CONFIDENCE, m.sentiment_confidence),
    ]
    for values, column in checks:
        worst = max(values, key=len)
        assert len(worst) <= column.type.length, column.name
    assert len(llm_sentiment.PROMPT_VERSION) <= \
        m.sentiment_prompt_version.type.length
    legacy_worst = max(('bullish', 'bearish', 'neutral', 'unclear'), key=len)
    assert len(legacy_worst) <= m.llm_sentiment.type.length


# ---- the judge gate (judge_gate.py) -----------------------------------------


def gate_on(monkeypatch):
    from features.radar import judge_gate
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', True)


def test_pending_honours_a_ticker_set_and_a_window(clean_posts):
    with flask_app.app_context():
        a = make_post('zztest-gate-a', ticker='ZZA')
        b = make_post('zztest-gate-b', ticker='ZZB')
        old = make_post('zztest-gate-old', ticker='ZZB', when=NOW - dt.timedelta(hours=30))

        only_b = {m.id for m, _ in llm_sentiment.pending(50, tickers={'ZZB'})}
        assert b in only_b and old in only_b and a not in only_b

        windowed = {m.id for m, _ in llm_sentiment.pending(
            50, tickers={'ZZB'}, since=NOW - dt.timedelta(hours=24))}
        assert windowed == {b}

        assert llm_sentiment.pending(50, tickers=frozenset()) == []


def test_run_pass_with_an_empty_gate_makes_no_call_and_books_nothing(clean_posts, monkeypatch):
    gate_on(monkeypatch)
    with flask_app.app_context():
        make_post('zztest-gate-lone', ticker='ZZLONE')      # one mention: under the floor
        client = FakeClient([])                             # any call would pop from empty
        spent_before = db.session.query(RadarLlmSpend).get(
            (dt.date.today(), llm_sentiment.PRIMARY_MODEL))
        calls_before = spent_before.calls if spent_before else 0

        judged = llm_sentiment.run_pass(client=client, limit=5, now=NOW)

        assert judged == 0
        assert client.messages.requests == []
        spent = db.session.query(RadarLlmSpend).get(
            (dt.date.today(), llm_sentiment.PRIMARY_MODEL))
        assert (spent.calls if spent else 0) == calls_before


def test_a_watched_tickers_backlog_inside_the_window_is_judged(clean_posts, monkeypatch):
    gate_on(monkeypatch)
    from conftest import _admin_id
    from models import RadarWatch
    with flask_app.app_context():
        RadarWatch.query.filter_by(ticker='ZZW').delete()
        db.session.add(RadarWatch(user_id=_admin_id(), ticker='ZZW', created_at=NOW))
        db.session.commit()
        fresh = make_post('zztest-gate-w-new', ticker='ZZW', when=NOW - dt.timedelta(hours=1))
        stale = make_post('zztest-gate-w-old', ticker='ZZW', when=NOW - dt.timedelta(hours=30))
        client = FakeClient([answer([entry(1)], usage=usage_of(100, 20))])
        try:
            judged = llm_sentiment.run_pass(client=client, limit=5, now=NOW)

            assert judged == 1
            assert db.session.get(RadarMention, fresh).sentiment_judged_at is not None
            assert db.session.get(RadarMention, stale).sentiment_judged_at is None
        finally:
            RadarWatch.query.filter_by(ticker='ZZW').delete()
            db.session.commit()


def test_ops_summary_counts_the_gated_backlog_apart_from_the_pending_one(clean_posts, monkeypatch):
    gate_on(monkeypatch)
    from conftest import _admin_id
    from models import RadarWatch
    with flask_app.app_context():
        RadarWatch.query.filter_by(ticker='ZZW').delete()
        db.session.add(RadarWatch(user_id=_admin_id(), ticker='ZZW', created_at=NOW))
        db.session.commit()
        make_post('zztest-ops-w', ticker='ZZW', when=NOW - dt.timedelta(hours=1))      # admitted
        make_post('zztest-ops-lone', ticker='ZZLONE', when=NOW - dt.timedelta(hours=1)) # held back
        make_post('zztest-ops-old', ticker='ZZW', when=NOW - dt.timedelta(hours=30))    # outside the window
        try:
            before = llm_sentiment.ops_summary(now=NOW)
            # Only the seeded rows carry these tickers; the dev DB's own
            # backlog is far older than NOW and outside the window.
            assert before['pending'] == 1
            assert before['gated_pending'] == 1
        finally:
            RadarWatch.query.filter_by(ticker='ZZW').delete()
            db.session.commit()
