# personal_apps/tests/test_radar_trial_writes.py
"""The trial write path: what a tone-suppressed backend does NOT write.

Almost every assertion here is an absence, which is the hardest kind to
trust. Four surfaces read attitude -- the post cards, the detail breakdown,
board.py's bull/bear CASE, and the legacy projection column -- so excluding
the encoder's tone by relabelling any one of them would leave the other
three showing it. The exclusion is therefore a WRITE decision: the column is
never set, and its absence is a fact about the database rather than a rule
somebody has to remember.

Each negative assertion here has a named mutation that makes it fail. They
were run and restored; the ledger records the results.
"""
import datetime as dt

import pytest

from app import app as flask_app
from extensions import db
from features.radar import (board, detail_panel, judge_backends,
                            llm_sentiment)
from models import (RadarMention, RadarMentionEvent, RadarPost,
                    RadarSentimentJudgment)

NOW = dt.datetime(2027, 1, 1, 12, 0, 0)
ENCODER = judge_backends.ENCODER_MODEL_ID
HAIKU = llm_sentiment.PRIMARY_MODEL
SONNET = llm_sentiment.REVIEW_MODEL


@pytest.fixture()
def clean_posts():
    with flask_app.app_context():
        _wipe()
        yield
        _wipe()


def _wipe():
    ids = [row.id for row in RadarPost.query.filter(
        RadarPost.external_id.like('zztrial%')).all()]
    if ids:
        RadarMentionEvent.query.filter(
            RadarMentionEvent.external_id.like('zztrial%')).delete(
            synchronize_session=False)
        RadarPost.query.filter(RadarPost.id.in_(ids)).delete(
            synchronize_session=False)
    db.session.commit()


def make_post(external_id, ticker='ZZT', body='ZZT ripping', when=NOW,
              lexicon=0.25):
    post = RadarPost(source='bluesky', external_id=external_id,
                     channel='firehose', author='someone', created_utc=when,
                     title=None, body=body, first_seen=when, last_seen=when)
    db.session.add(post)
    db.session.flush()
    mention = RadarMention(post_id=post.id, ticker=ticker, confidence='high',
                           lexicon_sentiment=lexicon)
    db.session.add(mention)
    db.session.commit()
    return mention.id


def rows_for(mention_ids):
    return (db.session.query(RadarMention, RadarPost)
            .join(RadarPost, RadarPost.id == RadarMention.post_id)
            .filter(RadarMention.id.in_(list(mention_ids))).all())


def ja(relevance='relevant', origin='human_chatter', attitude='positive',
       move='up', confidence='high', input_tokens=0, output_tokens=0):
    return llm_sentiment.JudgedAnswer(
        judgment=llm_sentiment.Judgment(relevance, origin, attitude, move,
                                        confidence),
        input_tokens=input_tokens, output_tokens=output_tokens)


def judge_as(mention_ids, answers, model=ENCODER, stage='primary',
             write_tone=False):
    written = llm_sentiment.apply_judgments(
        rows_for(mention_ids), answers, stage=stage, model=model,
        write_tone=write_tone)
    db.session.commit()
    return written


TONE_COLUMNS = ('sentiment_attitude', 'sentiment_expected_move',
                'sentiment_confidence', 'llm_sentiment')


# ---- 1. a fresh row: tone columns never acquire a value ---------------------

def test_a_suppressed_primary_writes_relevance_and_no_tone(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-fresh')
        assert judge_as([mention_id], {mention_id: ja()}) == 1

        m = db.session.get(RadarMention, mention_id)
        for column in TONE_COLUMNS:
            assert getattr(m, column) is None, column
        assert m.sentiment_relevance == 'relevant'
        assert m.sentiment_content_origin == 'human_chatter'
        assert m.sentiment_model == ENCODER
        assert m.sentiment_prompt_version == llm_sentiment.PROMPT_VERSION
        assert m.sentiment_judged_at is not None


def test_the_history_row_carries_all_five_fields_anyway(clean_posts):
    """Suppressed in production, captured for evaluation. The trial is
    pointless if its tone answers are not recorded somewhere."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-history')
        judge_as([mention_id], {mention_id: ja(attitude='negative',
                                               move='down',
                                               confidence='medium')})
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).one()
        assert (history.relevance, history.content_origin, history.attitude,
                history.expected_move, history.confidence) == \
            ('relevant', 'human_chatter', 'negative', 'down', 'medium')
        assert history.stage == 'primary' and history.model == ENCODER


# ---- 2. an already-toned row: suppression preserves, never clears -----------

def test_a_suppressed_primary_preserves_an_existing_tone(clean_posts):
    """Suppression means DO NOT WRITE, not write NULL. Clearing would
    silently delete a real Anthropic verdict the board is showing."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-preserve')
        judge_as([mention_id], {mention_id: ja(attitude='negative',
                                               move='down',
                                               confidence='medium')},
                 model=HAIKU, write_tone=True)
        before = db.session.get(RadarMention, mention_id)
        kept = {column: getattr(before, column) for column in TONE_COLUMNS}
        assert all(value is not None for value in kept.values())

        judge_as([mention_id], {mention_id: ja(attitude='positive',
                                               move='up')})

        after = db.session.get(RadarMention, mention_id)
        for column, value in kept.items():
            assert getattr(after, column) == value, column
        # ...while the fields the trial IS allowed to move did move.
        assert after.sentiment_model == ENCODER


# ---- 3. the projection is not merely unwritten, it is not called -----------

def test_the_legacy_projection_is_never_computed(clean_posts, monkeypatch):
    """llm_sentiment stays NULL even if the projection is computed and
    thrown away -- so poison the function itself."""
    def boom(judgment):
        raise AssertionError('legacy_projection ran on a suppressed write')

    monkeypatch.setattr(llm_sentiment, 'legacy_projection', boom)
    with flask_app.app_context():
        mention_id = make_post('zztrial-projection')
        assert judge_as([mention_id], {mention_id: ja()}) == 1


# ---- 4. the four surfaces that read attitude -------------------------------

def test_the_post_card_tone_is_unchanged_by_a_suppressed_judgment(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-card', lexicon=0.8)
        before = detail_panel._tone_of(0.8, None, None)
        judge_as([mention_id], {mention_id: ja(attitude='negative',
                                               move='down')})
        m = db.session.get(RadarMention, mention_id)
        after = detail_panel._tone_of(m.lexicon_sentiment, m.llm_sentiment,
                                      m.sentiment_attitude)
        assert after == before == 'bullish'
        assert detail_panel._judged_by(m.lexicon_sentiment, m.llm_sentiment,
                                       m.sentiment_attitude) == 'lexicon'


def test_a_legacy_tone_still_wins_over_the_lexicon_after_the_trial_judges(
        clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-legacy', lexicon=0.8)
        m = db.session.get(RadarMention, mention_id)
        m.llm_sentiment = 'bearish'          # a pre-v2 verdict
        db.session.commit()

        judge_as([mention_id], {mention_id: ja(attitude='positive')})

        m = db.session.get(RadarMention, mention_id)
        assert detail_panel._tone_of(m.lexicon_sentiment, m.llm_sentiment,
                                     m.sentiment_attitude) == 'bearish'
        assert detail_panel._judged_by(m.lexicon_sentiment, m.llm_sentiment,
                                       m.sentiment_attitude) == 'model'


def test_the_board_bull_bear_case_counts_the_same_before_and_after(
        clean_posts):
    """board.py:358 reads the columns directly in SQL, so this asks the
    real query rather than re-implementing its precedence."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-board', ticker='ZZT', lexicon=0.8)
        since, until = NOW - dt.timedelta(hours=1), NOW + dt.timedelta(hours=1)
        before = board._tones(['ZZT'], ['bluesky'], since, until)
        assert before, 'the fixture must be inside the counted window'

        judge_as([mention_id], {mention_id: ja(attitude='negative',
                                               move='down')})

        assert board._tones(['ZZT'], ['bluesky'], since, until) == before


# ---- 5. the point of the trial: removals DO take effect --------------------

@pytest.mark.parametrize('answer,eligible', [
    (ja(relevance='irrelevant', attitude='none', move='unknown'), False),
    (ja(origin='broadcast_or_automated'), False),
    (ja(), True),
    (ja(relevance='uncertain'), None),
    (ja(origin='uncertain'), None),
])
def test_eligibility_follows_the_suppressed_verdict(clean_posts, answer,
                                                    eligible):
    with flask_app.app_context():
        mention_id = make_post('zztrial-eligibility')
        judge_as([mention_id], {mention_id: answer})
        m = db.session.get(RadarMention, mention_id)
        assert llm_sentiment.final_eligibility(m) is eligible


def test_a_suppressed_removal_reaches_the_journal(clean_posts):
    """Not just the mention column: the whole reason the trial exists is
    that these verdicts leave the counts."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-journal', ticker='ZZT')
        post = db.session.get(RadarMention, mention_id).post
        db.session.add(RadarMentionEvent(
            source='bluesky', external_id=post.external_id, ticker='ZZT',
            confidence='high', created_utc=NOW,
            bucket_start=NOW.replace(minute=0, second=0, microsecond=0),
            promoted=False, counts_as_human_chatter=None))
        db.session.commit()

        rows = rows_for([mention_id])
        answers = {mention_id: ja(relevance='irrelevant', attitude='none',
                                  move='unknown')}
        llm_sentiment.apply_judgments(rows, answers, stage='primary',
                                      model=ENCODER, write_tone=False)
        changed = llm_sentiment._sync_eligibility(rows, answers)
        db.session.commit()

        event = RadarMentionEvent.query.filter_by(
            source='bluesky', external_id=post.external_id,
            ticker='ZZT').one()
        assert event.counts_as_human_chatter is False
        assert changed


# ---- 6. the pass does not loop on its own rows ------------------------------

def test_a_suppressed_row_is_not_pending_again(clean_posts):
    """pending() keys on sentiment_judged_at, which IS written -- otherwise
    the trial would rejudge the same rows every ten minutes forever."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-pending')
        assert mention_id in {m.id for m, _p in llm_sentiment.pending(200)}
        judge_as([mention_id], {mention_id: ja()})
        assert mention_id not in {m.id for m, _p in llm_sentiment.pending(200)}


# ---- 7. training never sees an encoder tone label ---------------------------

def test_fresh_trial_rows_are_not_training_data(clean_posts):
    from scripts import train_radar_sentiment as trainer
    with flask_app.app_context():
        mention_id = make_post('zztrial-training', body='great stuff here')
        post_id = db.session.get(RadarMention, mention_id).post_id
        judge_as([mention_id], {mention_id: ja()})
        assert post_id not in {row['post_id'] for row in trainer.load_rows()}


def test_a_preserved_anthropic_tone_stays_training_eligible(clean_posts):
    """The invariant is that no ENCODER-generated tone label enters
    training -- not that every mention the encoder ever saw is excluded.
    This row's label is still Haiku's, and it is still true."""
    from scripts import train_radar_sentiment as trainer
    with flask_app.app_context():
        mention_id = make_post('zztrial-training-kept', body='great stuff')
        judge_as([mention_id], {mention_id: ja(confidence='high')},
                 model=HAIKU, write_tone=True)
        judge_as([mention_id], {mention_id: ja(attitude='negative')})

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'positive'      # Haiku's, preserved
        rows = [row for row in trainer.load_rows()
                if row['post_id'] == m.post_id]
        assert rows and rows[0]['label'] == 'positive'


# ---- 8. review routing reads history, not the mention -----------------------

def test_review_routing_reads_the_history_not_the_null_columns(clean_posts,
                                                               monkeypatch):
    """The trigger is `confidence == 'low'`, and the mention's confidence
    column is NULL during the trial. Only the history row knows."""
    real = llm_sentiment.review_candidates
    monkeypatch.setattr(llm_sentiment, 'review_candidates',
                        lambda now, limit=llm_sentiment.PASS_LIMIT: [
                            (m, p) for m, p in real(now, limit)
                            if p.external_id.startswith('zztrial')])
    with flask_app.app_context():
        mention_id = make_post('zztrial-routing')
        judge_as([mention_id], {mention_id: ja(confidence='low')})

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_confidence is None
        assert mention_id in {mention.id for mention, _post
                              in llm_sentiment.review_candidates(NOW)}


def test_the_router_prefers_the_newest_primary_history(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-newest')
        judge_as([mention_id], {mention_id: ja(confidence='low')})
        judge_as([mention_id], {mention_id: ja(confidence='high')})

        history = llm_sentiment.latest_primary_history([mention_id])
        assert history[mention_id].confidence == 'high'
        judgment = llm_sentiment._judgment_of(
            db.session.get(RadarMention, mention_id), history[mention_id])
        assert judgment.confidence == 'high'


def test_a_stale_mention_tone_is_never_mixed_into_a_history_judgment(
        clean_posts):
    """Relevance from one judgment and attitude from another is a judgment
    nobody made, and it would route review spend at a contradiction that
    does not exist."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-mixed', lexicon=0.9)
        judge_as([mention_id], {mention_id: ja(attitude='positive')},
                 model=HAIKU, write_tone=True)
        judge_as([mention_id], {mention_id: ja(attitude='negative',
                                               move='down')})

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'positive'      # preserved, stale
        history = llm_sentiment.latest_primary_history([mention_id])
        judgment = llm_sentiment._judgment_of(m, history[mention_id])
        assert judgment.attitude == 'negative'         # the encoder's own
        assert judgment.relevance == 'relevant'


def test_a_missing_history_row_falls_back_only_for_a_tone_writing_model(
        clean_posts):
    with flask_app.app_context():
        legacy_id = make_post('zztrial-fallback-ok')
        m = db.session.get(RadarMention, legacy_id)
        m.sentiment_relevance = 'relevant'
        m.sentiment_content_origin = 'human_chatter'
        m.sentiment_attitude = 'positive'
        m.sentiment_expected_move = 'up'
        m.sentiment_confidence = 'low'
        m.sentiment_model = HAIKU
        m.sentiment_prompt_version = llm_sentiment.PROMPT_VERSION
        m.sentiment_judged_at = NOW
        db.session.commit()
        assert llm_sentiment._judgment_of(m, None).confidence == 'low'

        # The same row, but written by the encoder: its tone columns cannot
        # be trusted to belong with its relevance, so there is no answer.
        m.sentiment_model = ENCODER
        db.session.commit()
        assert llm_sentiment._judgment_of(m, None) is None


def test_an_incomplete_mention_is_skipped_not_defaulted(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-incomplete')
        m = db.session.get(RadarMention, mention_id)
        m.sentiment_relevance = 'relevant'
        m.sentiment_model = HAIKU
        m.sentiment_judged_at = NOW
        db.session.commit()
        assert llm_sentiment._judgment_of(m, None) is None


# ---- 9. an enabled Anthropic review keeps its own policy --------------------

def test_a_review_writes_its_own_tone_over_a_suppressed_primary(clean_posts):
    """The review judges the prepared text independently. It does not
    inherit the primary's suppression, and it never promotes the encoder's
    stored answer into a review verdict."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-review')
        judge_as([mention_id], {mention_id: ja(attitude='negative',
                                               move='down')})
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude is None

        judge_as([mention_id], {mention_id: ja(attitude='positive')},
                 model=SONNET, stage='review', write_tone=True)

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_attitude == 'positive'
        assert m.sentiment_model == SONNET
        assert m.llm_sentiment == 'bullish'
        stages = [h.stage for h in RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).order_by(RadarSentimentJudgment.id).all()]
        assert stages == ['primary', 'review']


def test_a_later_suppressed_primary_cannot_undo_a_review(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-review-stands')
        judge_as([mention_id], {mention_id: ja()})
        judge_as([mention_id], {mention_id: ja(attitude='positive')},
                 model=SONNET, stage='review', write_tone=True)
        judge_as([mention_id], {mention_id: ja(relevance='irrelevant',
                                               attitude='none',
                                               move='unknown')})

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_model == SONNET
        assert m.sentiment_relevance == 'relevant'
        assert m.sentiment_attitude == 'positive'


# ---- 10. the policy comes from the backend, not the call site ---------------

def test_the_encoder_declares_that_it_does_not_write_tone():
    assert judge_backends.EncoderBackend.writes_tone is False
    assert judge_backends.AnthropicBackend.writes_tone is True


def test_a_backend_with_no_declared_policy_is_refused():
    """A new backend must not quietly acquire the permissive policy."""
    class Undeclared:
        id = 'zz-undeclared'

    with pytest.raises(ValueError):
        judge_backends.writes_tone(Undeclared())


def test_a_stored_encoder_id_is_known_not_to_own_its_tone():
    assert judge_backends.writes_tone_for_model(ENCODER) is False
    assert judge_backends.writes_tone_for_model(HAIKU) is True
    assert judge_backends.writes_tone_for_model(SONNET) is True


# ---- 11. the wiring, not just the writer ------------------------------------

class ToneFreeBackend:
    """A backend that declares the encoder's policy and answers offline.

    Everything above calls apply_judgments directly, which proves the WRITER
    honours write_tone. This proves the PASS reads the policy off the
    backend it was handed -- without it, `write_tone=writes_tone(backend)`
    could be replaced by a literal True and every test above would still
    pass.
    """

    id = ENCODER
    batch_size = 4
    pass_limit = 400
    supports_review = False
    writes_tone = False

    def __init__(self, answers):
        self.answers = answers

    def judge_batch(self, batch, *, preamble=None):
        return ({item.key: self.answers[item.key].judgment
                 for item in batch if item.key in self.answers},
                judge_backends.Usage(0, 0))


def test_the_pass_takes_its_tone_policy_from_the_backend(clean_posts,
                                                         monkeypatch):
    from features.radar import judge_gate
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)
    with flask_app.app_context():
        mention_id = make_post('zztrial-wiring')
        backend = ToneFreeBackend({mention_id: ja(attitude='negative',
                                                  move='down')})

        assert llm_sentiment.run_pass(backend=backend, limit=5) >= 1

        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_model == ENCODER
        assert m.sentiment_relevance == 'relevant'
        for column in TONE_COLUMNS:
            assert getattr(m, column) is None, column
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).one()
        assert history.attitude == 'negative'
