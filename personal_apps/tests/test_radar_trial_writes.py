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
    from features.radar import judge_gate, judge_trial
    from models import RadarJudgeTrial
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)
    with flask_app.app_context():
        RadarJudgeTrial.query.delete(synchronize_session=False)
        db.session.commit()
        # The encoder may not judge without an armed trial: the armed row
        # is what pins the journal its recovery would need.
        judge_trial.arm_trial(dt.datetime.utcnow(), artifact_sha256='a' * 64,
                              baseline_report='reports/baseline.json',
                              baseline_removal_rate=0.3, seed=1)
        try:
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
            # ...and the deadline clock started with that first verdict.
            row = judge_trial.current()
            assert row.first_judged_at is not None
            assert row.status == judge_trial.RUNNING
        finally:
            RadarJudgeTrial.query.delete(synchronize_session=False)
            db.session.commit()


def test_the_encoder_will_not_judge_without_an_armed_trial(clean_posts,
                                                           monkeypatch):
    """Without a trial there is no pin holding the evidence, so the very
    first judgment would already be unrecoverable."""
    from features.radar import judge_gate, judge_trial
    from models import RadarJudgeTrial
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)
    with flask_app.app_context():
        RadarJudgeTrial.query.delete(synchronize_session=False)
        db.session.commit()
        mention_id = make_post('zztrial-noarm')
        backend = ToneFreeBackend({mention_id: ja()})

        with pytest.raises(judge_trial.TrialError):
            llm_sentiment.run_pass(backend=backend, limit=5)

        assert db.session.get(RadarMention,
                              mention_id).sentiment_judged_at is None


# ---- 12. tone provenance ----------------------------------------------------
#
# `sentiment_model` answers "who judged this mention". Once a backend can
# judge relevance without writing tone, that stops answering "whose tone is
# on screen" -- and the post card was printing a hardcoded 'Claude' for
# both. These pin the second question apart from the first.

def test_a_suppressed_write_leaves_tone_provenance_alone(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-prov-fresh')
        judge_as([mention_id], {mention_id: ja()})
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_model == ENCODER
        assert m.sentiment_tone_model is None


def test_tone_provenance_is_written_with_the_tone(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-prov-haiku')
        judge_as([mention_id], {mention_id: ja()}, model=HAIKU,
                 write_tone=True)
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_tone_model == HAIKU


def test_a_suppressed_write_preserves_an_existing_tone_owner(clean_posts):
    """The board is still showing Haiku's tone, so the row must still say
    Haiku owns it -- even though the encoder judged the mention last."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-prov-keep')
        judge_as([mention_id], {mention_id: ja()}, model=HAIKU,
                 write_tone=True)
        judge_as([mention_id], {mention_id: ja(attitude='negative')})
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_model == ENCODER
        assert m.sentiment_tone_model == HAIKU
        assert m.sentiment_attitude == 'positive'


def test_a_review_takes_over_tone_ownership(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-prov-review')
        judge_as([mention_id], {mention_id: ja()}, model=HAIKU,
                 write_tone=True)
        judge_as([mention_id], {mention_id: ja(attitude='negative')},
                 model=SONNET, stage='review', write_tone=True)
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_tone_model == SONNET


def test_a_blocked_primary_does_not_touch_tone_ownership(clean_posts):
    """The standing-review guard covers provenance too."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-prov-blocked')
        judge_as([mention_id], {mention_id: ja()}, model=SONNET,
                 stage='review', write_tone=True)
        judge_as([mention_id], {mention_id: ja(attitude='negative')},
                 model=HAIKU, write_tone=True)
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_tone_model == SONNET
        assert m.sentiment_model == SONNET


# ---- 13. what production was showing when the encoder answered --------------

def test_a_suppressed_history_row_records_the_displayed_tone(clean_posts):
    """The five fields are what the encoder SAID; these three are what
    production DID. The trial's tone comparison needs both halves."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-diag', lexicon=0.8)
        judge_as([mention_id], {mention_id: ja(attitude='negative',
                                               move='down')})
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).one()
        assert history.attitude == 'negative'          # what it said
        assert history.displayed_tone == 'bullish'     # what was on screen
        assert history.displayed_judged_by == 'lexicon'
        assert history.displayed_tone_model is None


def test_the_diagnostics_record_a_preserved_model_tone(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-diag-model', lexicon=0.8)
        judge_as([mention_id], {mention_id: ja(attitude='positive')},
                 model=HAIKU, write_tone=True)
        judge_as([mention_id], {mention_id: ja(attitude='negative',
                                               move='down')})
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id, model=ENCODER).one()
        assert history.displayed_tone == 'bullish'
        assert history.displayed_judged_by == 'model'
        assert history.displayed_tone_model == HAIKU


def test_an_unscored_mention_records_neutral_not_null(clean_posts):
    """'neutral' is what the card shows for a mention nothing has scored,
    so that is what production was displaying."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-diag-none')
        m = db.session.get(RadarMention, mention_id)
        m.lexicon_sentiment = None
        db.session.commit()
        judge_as([mention_id], {mention_id: ja()})
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).one()
        assert history.displayed_tone == 'neutral'
        assert history.displayed_judged_by is None


def test_a_tone_writing_backend_records_no_display_diagnostics(clean_posts):
    """They exist to compare a suppressed answer against what was shown.
    When the answer IS what is shown there is nothing to compare."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-diag-haiku')
        judge_as([mention_id], {mention_id: ja()}, model=HAIKU,
                 write_tone=True)
        history = RadarSentimentJudgment.query.filter_by(
            mention_id=mention_id).one()
        assert history.displayed_tone is None
        assert history.displayed_tone_model is None
        assert history.displayed_judged_by is None


# ---- 14. the label on the post card -----------------------------------------

def test_the_card_names_the_model_that_owns_the_tone(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-label', ticker='ZZL')
        judge_as([mention_id], {mention_id: ja()}, model=HAIKU,
                 write_tone=True)
        posts, _total = detail_panel._posts(
            'ZZL', ['bluesky'], NOW - dt.timedelta(hours=1),
            NOW + dt.timedelta(hours=1))
        assert [(tone, judged_by, label)
                for _p, tone, judged_by, label in posts] == \
            [('bullish', 'model', 'Claude')]


def test_a_lexicon_tone_carries_no_model_name(clean_posts):
    with flask_app.app_context():
        mention_id = make_post('zztrial-label-lex', ticker='ZZM', lexicon=0.8)
        judge_as([mention_id], {mention_id: ja()})
        posts, _total = detail_panel._posts(
            'ZZM', ['bluesky'], NOW - dt.timedelta(hours=1),
            NOW + dt.timedelta(hours=1))
        assert [(judged_by, label) for _p, _t, judged_by, label in posts] == \
            [('lexicon', None)]


def test_an_unidentifiable_owner_is_labelled_generically(clean_posts):
    """A legacy row whose tone ownership was never recorded, or a future
    backend this build has never heard of. 'model' is true of both and
    claims nothing further."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-label-legacy', ticker='ZZN')
        m = db.session.get(RadarMention, mention_id)
        m.llm_sentiment = 'bullish'
        db.session.commit()
        posts, _total = detail_panel._posts(
            'ZZN', ['bluesky'], NOW - dt.timedelta(hours=1),
            NOW + dt.timedelta(hours=1))
        assert [(judged_by, label) for _p, _t, judged_by, label in posts] == \
            [('model', 'model')]


def test_the_label_never_speaks_for_a_tone_the_encoder_did_not_write(
        clean_posts):
    """The trap this whole column exists for: the encoder judged the
    mention last, so sentiment_model is the encoder -- but the tone on
    screen is still Haiku's and must still say so."""
    with flask_app.app_context():
        mention_id = make_post('zztrial-label-trap', ticker='ZZO')
        judge_as([mention_id], {mention_id: ja()}, model=HAIKU,
                 write_tone=True)
        judge_as([mention_id], {mention_id: ja(attitude='negative')})
        m = db.session.get(RadarMention, mention_id)
        assert m.sentiment_model == ENCODER
        posts, _total = detail_panel._posts(
            'ZZO', ['bluesky'], NOW - dt.timedelta(hours=1),
            NOW + dt.timedelta(hours=1))
        assert [label for _p, _t, _j, label in posts] == ['Claude']


# ---- 15. spend --------------------------------------------------------------

def test_every_backend_this_build_can_run_is_priced():
    """A missing rate is not a small thing: cost_micros returns None and
    the board reports those tokens as `unpriced` forever."""
    from features.radar import spend
    for model_id in (HAIKU, SONNET, ENCODER):
        assert model_id in spend.MODEL_RATES, model_id
        assert len(model_id) <= 40, model_id


def test_a_free_backend_costs_zero_not_unknown():
    from features.radar import spend
    assert spend.cost_micros(ENCODER, 10000, 2000) == 0
    assert spend.cost_micros('claude-not-a-real-model', 10000, 2000) is None


def test_the_sonnet_rate_is_list_price():
    from features.radar import spend
    assert spend.MODEL_RATES[SONNET] == (2.00, 10.00)



def test_answers_that_outlive_their_trial_are_discarded(clean_posts,
                                                        monkeypatch):
    """A batch can outlive the trial it belongs to: a stop, a failed audit
    or the deadline can land while it is in flight. A late answer must be
    thrown away, not stored under a trial that has ended -- otherwise a
    stop leaves judgments arriving after it.
    """
    from features.radar import judge_gate, judge_trial
    from models import RadarJudgeTrial
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)

    with flask_app.app_context():
        RadarJudgeTrial.query.delete(synchronize_session=False)
        db.session.commit()
        judge_trial.arm_trial(dt.datetime.utcnow(), artifact_sha256='a' * 64,
                              baseline_report='reports/baseline.json',
                              baseline_removal_rate=0.3, seed=1)
        try:
            mention_id = make_post('zztrial-inflight')

            class StopsMidFlight(ToneFreeBackend):
                def judge_batch(self, batch, *, preamble=None):
                    answers = super().judge_batch(batch, preamble=preamble)
                    # The operator stops the trial while this batch is out.
                    judge_trial.request_stop('stopped mid-flight')
                    return answers

            backend = StopsMidFlight({mention_id: ja()})
            assert llm_sentiment.run_pass(backend=backend, limit=5) == 0

            m = db.session.get(RadarMention, mention_id)
            assert m.sentiment_judged_at is None
            assert m.sentiment_relevance is None
            assert RadarSentimentJudgment.query.filter_by(
                mention_id=mention_id).count() == 0
        finally:
            RadarJudgeTrial.query.delete(synchronize_session=False)
            db.session.commit()


# ---- 14. the write boundary: a stop from ANOTHER process --------------------
#
# The stop, the deadline and recovery all happen in other processes -- the
# CLI, the watchdog timer -- and a daemon session cannot see their commits
# through its identity map or its repeatable-read snapshot. A plain re-read
# of the trial row after inference therefore proves nothing: it answers from
# memory. Only a LOCKING read sees what the database holds now, and only a
# lock held until the verdicts commit keeps that answer true while writing.
# These drive the pass with a trial row changed on a separate connection,
# the way every other process changes it.

import sqlalchemy.exc

LOCK_REFUSED = 3572          # MySQL: NOWAIT could not acquire the row lock


def arm_now(**overrides):
    from features.radar import judge_trial
    from models import RadarJudgeTrial
    RadarJudgeTrial.query.delete(synchronize_session=False)
    db.session.commit()
    row = judge_trial.arm_trial(overrides.pop('now', dt.datetime.utcnow()),
                                artifact_sha256='a' * 64,
                                baseline_report='reports/baseline.json',
                                baseline_removal_rate=0.3, seed=1)
    for field, value in overrides.items():
        setattr(row, field, value)
    db.session.commit()
    return row


def drop_trial():
    from models import RadarJudgeTrial
    db.session.rollback()
    RadarJudgeTrial.query.delete(synchronize_session=False)
    db.session.commit()


def from_another_process(sql, *params):
    """Run one statement the way the CLI or the timer would: on its own
    connection, committed, invisible to this session's open snapshot."""
    with db.engine.connect() as other:
        result = other.exec_driver_sql(sql, params)
        rows = result.fetchall() if result.returns_rows else None
        other.commit()
        return rows


def trial_as_stored():
    (status, first_judged_at), = from_another_process(
        'SELECT status, first_judged_at FROM radar_judge_trial WHERE id = 1')
    return status, first_judged_at


def test_a_stop_from_another_process_is_seen_before_anything_is_written(
        clean_posts, monkeypatch):
    """The operator stops the trial from the CLI while a batch is out. The
    daemon session has already read the row as `armed`; only a locking
    read sees the stop, and a stopped trial must not be resurrected by the
    first-judgment clock either."""
    from features.radar import judge_gate, judge_trial
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)

    with flask_app.app_context():
        arm_now()
        try:
            mention_id = make_post('zztrial-cross-stop')

            class StoppedElsewhere(ToneFreeBackend):
                def judge_batch(self, batch, *, preamble=None):
                    answers = super().judge_batch(batch, preamble=preamble)
                    from_another_process(
                        'UPDATE radar_judge_trial SET status = %s, '
                        'stop_reason = %s WHERE id = 1',
                        judge_trial.RECOVERING, 'stopped from the CLI')
                    return answers

            backend = StoppedElsewhere({mention_id: ja()})
            assert llm_sentiment.run_pass(backend=backend, limit=5) == 0

            m = db.session.get(RadarMention, mention_id)
            assert m.sentiment_judged_at is None
            assert RadarSentimentJudgment.query.filter_by(
                mention_id=mention_id).count() == 0
            # Still stopped, and its clock never started.
            assert trial_as_stored() == (judge_trial.RECOVERING, None)
        finally:
            drop_trial()


def test_the_trial_row_stays_locked_while_the_verdicts_are_written(
        clean_posts, monkeypatch):
    """Validating the trial and then writing without holding it is a gap a
    stop can land in. The row lock must be held from the check through the
    commit -- another process asking for it meanwhile must be refused."""
    from features.radar import judge_gate
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)

    def probe():
        with db.engine.connect() as other:
            try:
                other.exec_driver_sql('SELECT status FROM radar_judge_trial '
                                      'WHERE id = 1 FOR UPDATE NOWAIT')
                return 'free'
            except sqlalchemy.exc.OperationalError as error:
                code = getattr(error.orig, 'args', (None,))[0]
                return 'locked' if code == LOCK_REFUSED else 'error'
            finally:
                other.rollback()

    with flask_app.app_context():
        arm_now()
        try:
            mention_id = make_post('zztrial-held-lock')
            real_apply = llm_sentiment.apply_judgments
            observed = []

            def apply_and_probe(*args, **kwargs):
                observed.append(probe())
                return real_apply(*args, **kwargs)

            monkeypatch.setattr(llm_sentiment, 'apply_judgments',
                                apply_and_probe)
            backend = ToneFreeBackend({mention_id: ja()})
            assert llm_sentiment.run_pass(backend=backend, limit=5) == 1

            assert observed == ['locked']
            assert probe() == 'free', 'the commit must release the row'
        finally:
            drop_trial()


def test_a_batch_after_the_deadline_is_not_even_sent(clean_posts,
                                                     monkeypatch):
    """A pass that starts one second before expiry and runs for minutes
    must not carry its starting clock through every batch. Each batch asks
    the time again, and a batch past the deadline is never judged."""
    import itertools
    from features.radar import judge_gate, judge_trial
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)

    with flask_app.app_context():
        started = dt.datetime.utcnow() - dt.timedelta(days=10) \
            + dt.timedelta(minutes=5)
        arm_now(now=started - dt.timedelta(hours=1), first_judged_at=started,
                status=judge_trial.RUNNING)
        ends = started + dt.timedelta(days=judge_trial.TRIAL_DEADLINE_DAYS)
        try:
            # Recent posts: the pass only reads mentions after the v2
            # activation cutoff, and the trial's tenth day is today.
            first = make_post('zztrial-clock-a',
                              when=dt.datetime.utcnow() - dt.timedelta(hours=2))
            second = make_post('zztrial-clock-b',
                               when=dt.datetime.utcnow() - dt.timedelta(hours=1))
            calls = []

            class OneAtATime(ToneFreeBackend):
                batch_size = 1

                def judge_batch(self, batch, *, preamble=None):
                    calls.append([item.key for item in batch])
                    return super().judge_batch(batch, preamble=preamble)

            # Pre-flight and the first batch see a live trial; the clock
            # then crosses the deadline before the second batch is sent.
            readings = itertools.chain(
                [ends - dt.timedelta(seconds=1)] * 2,
                itertools.repeat(ends + dt.timedelta(seconds=1)))
            backend = OneAtATime({first: ja(), second: ja()})

            judged = llm_sentiment.run_pass(
                backend=backend, limit=5, now=ends - dt.timedelta(seconds=1),
                clock=lambda: next(readings))

            assert judged == 0
            assert len(calls) == 1, calls
            for mention_id in (first, second):
                assert db.session.get(
                    RadarMention, mention_id).sentiment_judged_at is None
        finally:
            drop_trial()


def test_answers_judged_before_the_deadline_are_not_written_after_it(
        clean_posts, monkeypatch):
    """Every batch was sent in time; the deadline lands before the write.
    The write boundary reads the clock again, and a late answer is
    discarded rather than stored under a trial that has ended."""
    import itertools
    from features.radar import judge_gate, judge_trial
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)

    with flask_app.app_context():
        started = dt.datetime.utcnow() - dt.timedelta(days=10) \
            + dt.timedelta(minutes=5)
        arm_now(now=started - dt.timedelta(hours=1), first_judged_at=started,
                status=judge_trial.RUNNING)
        ends = started + dt.timedelta(days=judge_trial.TRIAL_DEADLINE_DAYS)
        try:
            mention_id = make_post('zztrial-clock-late',
                                   when=dt.datetime.utcnow() - dt.timedelta(hours=1))
            # Pre-flight and the single batch are in time; the boundary is
            # not.
            readings = itertools.chain(
                [ends - dt.timedelta(seconds=1)] * 2,
                itertools.repeat(ends + dt.timedelta(seconds=1)))
            backend = ToneFreeBackend({mention_id: ja()})

            judged = llm_sentiment.run_pass(
                backend=backend, limit=5, now=ends - dt.timedelta(seconds=1),
                clock=lambda: next(readings))

            assert judged == 0
            assert db.session.get(
                RadarMention, mention_id).sentiment_judged_at is None
        finally:
            drop_trial()


def test_a_mention_older_than_the_retained_interval_is_never_picked(
        clean_posts, monkeypatch):
    """With the judge gate off, the pass would otherwise reach back into a
    30-day backlog -- and recovery refuses any window that starts before
    the pin, because its journal is gone. So the pass must not take what
    recovery could not give back (spec §7.2a)."""
    from features.radar import judge_gate
    monkeypatch.setattr(judge_gate, 'JUDGE_GATE_ENABLED', False)

    with flask_app.app_context():
        now = dt.datetime.utcnow()
        arm_now(now=now)
        try:
            old = make_post('zztrial-retain-old',
                            when=now - dt.timedelta(days=3))
            fresh = make_post('zztrial-retain-fresh',
                              when=now - dt.timedelta(hours=1))
            backend = ToneFreeBackend({old: ja(), fresh: ja()})

            assert llm_sentiment.run_pass(backend=backend, limit=5,
                                          now=now) == 1

            assert db.session.get(RadarMention,
                                  old).sentiment_judged_at is None
            assert db.session.get(RadarMention,
                                  fresh).sentiment_judged_at is not None
        finally:
            drop_trial()
