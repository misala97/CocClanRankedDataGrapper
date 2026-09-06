# personal_apps/tests/test_radar_judge_config.py
"""Which judge runs, and where a misconfiguration is allowed to fail.

The default is `none`, and that is the load-bearing decision here: a deploy
that forgets a variable judges nothing. Judging with the wrong backend is
worse than not judging, because the wrong answers are stored, counted, and
attributed to whoever the id says.

The second decision is WHERE it fails. Resolution and construction happen at
startup, outside the exception handler that keeps a failing enrichment from
taking the daemon down -- because a misconfigured judge caught inside that
handler becomes a warning logged every ten minutes and read never.
"""
import datetime as dt
import os

import pytest

from app import app as flask_app
from extensions import db
from features.radar import judge_backends, judge_config, judge_trial
from features.radar.judge_config import ConfigError
from models import RadarJudgeTrial

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'fixtures', 'radar_encoder')


@pytest.fixture(autouse=True)
def clean_registry():
    judge_config.reset_for_tests()
    yield
    judge_config.reset_for_tests()


@pytest.fixture()
def no_trial():
    with flask_app.app_context():
        RadarJudgeTrial.query.delete(synchronize_session=False)
        db.session.commit()
        yield
        RadarJudgeTrial.query.delete(synchronize_session=False)
        db.session.commit()


def armed(**over):
    fields = dict(artifact_sha256=judge_backends.EncoderBackend(
        FIXTURE).bundle_sha256(),
        baseline_report='reports/baseline.json',
        baseline_removal_rate=0.3, seed=1)
    fields.update(over)
    return judge_trial.arm_trial(dt.datetime.utcnow(), **fields)


# ---- resolving ---------------------------------------------------------------

def test_an_empty_environment_judges_nothing():
    """The default a forgotten deploy variable produces."""
    settings = judge_config.resolve_settings({})
    assert settings.primary is None and settings.review is None
    assert settings.review_mode == judge_config.OFF
    assert settings.write_encoder_tone is False


@pytest.mark.parametrize('value', ['none', '', '   '])
def test_none_and_blank_both_mean_disabled(value):
    settings = judge_config.resolve_settings({'RADAR_JUDGE_PRIMARY': value})
    assert settings.primary is None


def test_a_spec_is_carried_through_verbatim():
    settings = judge_config.resolve_settings({
        'RADAR_JUDGE_PRIMARY': 'encoder',
        'RADAR_JUDGE_REVIEW': 'anthropic:claude-sonnet-5',
        'RADAR_JUDGE_ARTIFACT_DIR': '/srv/artifacts'})
    assert settings.primary == 'encoder'
    assert settings.review == 'anthropic:claude-sonnet-5'
    assert settings.artifact_dir == '/srv/artifacts'


@pytest.mark.parametrize('value', ['1', 'true', 'yes', 'on'])
def test_tone_cannot_be_switched_on_by_configuration(value):
    """Meeting the tone criteria is evidence for a later reviewed change.
    If a variable could flip it, the trial's central claim -- that encoder
    tone never reaches a reader -- would depend on an environment file."""
    with pytest.raises(ConfigError):
        judge_config.resolve_settings({'RADAR_JUDGE_TONE': value})


def test_tone_zero_is_accepted():
    assert judge_config.resolve_settings(
        {'RADAR_JUDGE_TONE': '0'}).write_encoder_tone is False


# ---- the review mode, and its two flags -------------------------------------

@pytest.mark.parametrize('environ,expected', [
    ({}, judge_config.OFF),
    ({'RADAR_SONNET_REVIEW': ''}, judge_config.OFF),
    ({'RADAR_SONNET_REVIEW': 'shadow'}, judge_config.SHADOW),
    ({'RADAR_SONNET_REVIEW': '1'}, judge_config.LIVE),
    ({'RADAR_SONNET_REVIEW': 'true'}, judge_config.LIVE),
    ({'RADAR_REVIEW_TIER': 'shadow'}, judge_config.SHADOW),
    ({'RADAR_REVIEW_TIER': '1'}, judge_config.LIVE),
])
def test_the_mode_reads_either_flag(environ, expected):
    assert judge_config.resolve_settings(environ).review_mode == expected


def test_an_empty_new_flag_still_wins_over_a_stale_old_one():
    """PRESENCE is the signal. Setting the new flag empty is how review is
    turned off without deleting the old one, and reading that as 'unset'
    would hand control back to a RADAR_SONNET_REVIEW nobody remembers."""
    environ = {'RADAR_REVIEW_TIER': '', 'RADAR_SONNET_REVIEW': '1'}
    assert judge_config.resolve_settings(environ).review_mode == \
        judge_config.OFF


def test_the_new_flag_overrides_the_old_one_when_both_are_set():
    environ = {'RADAR_REVIEW_TIER': 'shadow', 'RADAR_SONNET_REVIEW': '1'}
    assert judge_config.resolve_settings(environ).review_mode == \
        judge_config.SHADOW


@pytest.mark.parametrize('environ', [
    {'RADAR_REVIEW_TIER': 'sometimes'},
    {'RADAR_SONNET_REVIEW': 'yes'},
    {'RADAR_SONNET_REVIEW': 'off'},
])
def test_an_unrecognised_mode_fails_loudly_rather_than_meaning_off(environ):
    """Both readers of this flag used to accept slightly different values,
    so a typo meant 'off' in one place and something else in another."""
    with pytest.raises(ConfigError):
        judge_config.resolve_settings(environ)


# ---- constructing ------------------------------------------------------------

def test_nothing_configured_constructs_nothing(no_trial):
    with flask_app.app_context():
        judge_config.initialize_judges(judge_config.resolve_settings({}))
    assert judge_config.active_primary() is None
    assert judge_config.active_review() is None


def test_an_anthropic_primary_needs_no_trial(no_trial):
    with flask_app.app_context():
        judge_config.initialize_judges(judge_config.resolve_settings(
            {'RADAR_JUDGE_PRIMARY': 'anthropic:claude-haiku-4-5'}))
    assert judge_config.active_primary().id == 'claude-haiku-4-5'


def test_the_encoder_refuses_to_start_without_an_armed_trial(no_trial):
    """Without one there is no pin holding the journal its recovery would
    need, so the first judgment would already be unrecoverable."""
    with flask_app.app_context():
        with pytest.raises(ConfigError):
            judge_config.initialize_judges(judge_config.resolve_settings(
                {'RADAR_JUDGE_PRIMARY': 'encoder',
                 'RADAR_JUDGE_ARTIFACT_DIR': FIXTURE}))


def test_the_encoder_starts_against_its_own_armed_trial(no_trial):
    with flask_app.app_context():
        armed()
        judge_config.initialize_judges(judge_config.resolve_settings(
            {'RADAR_JUDGE_PRIMARY': 'encoder',
             'RADAR_JUDGE_ARTIFACT_DIR': FIXTURE}))
        assert judge_config.active_primary().id == 'radar-encoder-v1'


def test_a_different_artifact_than_the_one_armed_is_refused(no_trial):
    """Replacing any one of the three files is a different trial: swapping
    the tokenizer alone changes every verdict and leaves the weights
    untouched."""
    with flask_app.app_context():
        armed(artifact_sha256='b' * 64)
        with pytest.raises(ConfigError) as caught:
            judge_config.initialize_judges(judge_config.resolve_settings(
                {'RADAR_JUDGE_PRIMARY': 'encoder',
                 'RADAR_JUDGE_ARTIFACT_DIR': FIXTURE}))
        assert 'does not match' in str(caught.value)


@pytest.mark.parametrize('status', [judge_trial.RECOVERING,
                                    judge_trial.RECOVERED])
def test_a_finished_trial_disables_judging_without_stopping_ingestion(
        no_trial, status, caplog):
    """A stale RADAR_JUDGE_PRIMARY=encoder surviving a rollback must not
    keep the daemon from running -- but it must not judge either."""
    with flask_app.app_context():
        row = armed()
        row.status = status
        db.session.commit()
        with caplog.at_level('WARNING'):
            judge_config.initialize_judges(judge_config.resolve_settings(
                {'RADAR_JUDGE_PRIMARY': 'encoder',
                 'RADAR_JUDGE_ARTIFACT_DIR': FIXTURE}))
    assert judge_config.active_primary() is None
    assert any(status in record.getMessage() for record in caplog.records)


def test_a_backend_that_cannot_review_is_refused_for_the_review_role(
        no_trial):
    """Review exists to be an INDEPENDENT second opinion. The student
    cannot review the question its own teacher set."""
    with flask_app.app_context():
        armed()
        with pytest.raises(ConfigError) as caught:
            judge_config.initialize_judges(judge_config.resolve_settings(
                {'RADAR_JUDGE_REVIEW': 'encoder',
                 'RADAR_JUDGE_ARTIFACT_DIR': FIXTURE}))
        assert 'review' in str(caught.value)


def test_an_unknown_spec_fails_startup(no_trial):
    with flask_app.app_context():
        with pytest.raises(ValueError):
            judge_config.initialize_judges(judge_config.resolve_settings(
                {'RADAR_JUDGE_PRIMARY': 'openai:gpt-5'}))


# ---- what the passes see -----------------------------------------------------

def test_a_review_backend_without_a_mode_reviews_nothing(no_trial,
                                                         monkeypatch):
    monkeypatch.delenv('RADAR_SONNET_REVIEW', raising=False)
    monkeypatch.delenv('RADAR_REVIEW_TIER', raising=False)
    with flask_app.app_context():
        judge_config.initialize_judges(judge_config.resolve_settings(
            {'RADAR_JUDGE_REVIEW': 'anthropic:claude-sonnet-5'}))
    assert judge_config.active_review() is None


def test_a_mode_without_a_backend_reviews_nothing(no_trial, monkeypatch):
    monkeypatch.setenv('RADAR_SONNET_REVIEW', 'shadow')
    with flask_app.app_context():
        judge_config.initialize_judges(judge_config.resolve_settings({}))
    assert judge_config.active_review() is None


def test_both_together_review(no_trial, monkeypatch):
    monkeypatch.setenv('RADAR_REVIEW_TIER', 'shadow')
    with flask_app.app_context():
        judge_config.initialize_judges(judge_config.resolve_settings(
            {'RADAR_JUDGE_REVIEW': 'anthropic:claude-sonnet-5',
             'RADAR_REVIEW_TIER': 'shadow'}))
    assert judge_config.active_review().id == 'claude-sonnet-5'


def test_an_unconfigured_pass_judges_nothing_and_calls_nothing(no_trial):
    """The inert default, end to end: no backend, no query, no write."""
    from features.radar import llm_sentiment
    with flask_app.app_context():
        judge_config.initialize_judges(judge_config.resolve_settings({}))
        assert llm_sentiment.run_pass() == 0


def test_an_unconfigured_review_pass_judges_nothing(no_trial, monkeypatch):
    from features.radar import llm_sentiment
    monkeypatch.setenv('RADAR_REVIEW_TIER', 'shadow')
    with flask_app.app_context():
        judge_config.initialize_judges(judge_config.resolve_settings({}))
        assert llm_sentiment.run_review_pass() == 0


def test_a_bad_flag_fails_startup_but_never_a_board_request(monkeypatch):
    """The strict parser is shared by the daemon's startup and the board's
    over-ceiling gauge. A typo must stop the daemon, where an operator sees
    it -- and must not turn every board request into a 500, where it means
    only that review is certainly not running."""
    from features.radar import llm_sentiment
    monkeypatch.setenv('RADAR_SONNET_REVIEW', 'yes')

    with pytest.raises(ConfigError):
        judge_config.resolve_settings()

    with flask_app.app_context():
        assert llm_sentiment._over_ceiling_gauge(dt.datetime.utcnow(), 0) == 0
