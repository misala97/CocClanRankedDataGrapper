# personal_apps/features/radar/judge_config.py
"""Which judge runs, decided once at startup and never in a scheduled pass.

Two rules shape everything here.

**The default is `none`.** A deploy that forgets a variable judges nothing.
Judging with the wrong backend is worse than not judging at all, because the
wrong answers are stored, counted, and attributed to whoever the id says.

**Startup is where configuration fails.** Resolution and construction happen
in `run_radar_ingest.main`, before any fetcher or scheduler exists and
OUTSIDE the exception handler that keeps a failing enrichment from killing
the daemon. A misconfiguration must stop the daemon visibly, not be caught
every ten minutes and logged into the same warning nobody reads twice.

Nothing here is read by a web request. Importing this module opens no
client, no model session and no artifact.
"""
import dataclasses
import logging
import os

logger = logging.getLogger('radar.judge_config')

DISABLED = 'none'

# Review modes. '' is off; shadow measures demand without calling; live
# calls. Both a MODE and a BACKEND are required to review -- either alone
# judges nothing, which is what stops a half-finished rollout from
# accidentally spending on Sonnet.
OFF, SHADOW, LIVE = '', 'shadow', 'live'
_LEGACY_LIVE = ('1', 'true', 'True')


class ConfigError(Exception):
    """The daemon cannot start with this configuration."""


@dataclasses.dataclass(frozen=True)
class Settings:
    primary: str | None          # backend spec, or None for disabled
    review: str | None
    review_mode: str             # OFF | SHADOW | LIVE
    write_encoder_tone: bool     # always False in this build
    artifact_dir: str | None


def _spec(environ, name):
    value = (environ.get(name) or '').strip()
    if not value or value == DISABLED:
        return None
    return value


def _review_mode(environ):
    """RADAR_REVIEW_TIER wins whenever it is PRESENT, empty included.

    Presence is the signal, not truthiness: setting it to empty is how an
    operator turns review off without deleting the old flag, and reading an
    empty new flag as "unset" would silently hand control back to a stale
    RADAR_SONNET_REVIEW nobody remembers setting.
    """
    if 'RADAR_REVIEW_TIER' in environ:
        value = (environ.get('RADAR_REVIEW_TIER') or '').strip()
        if not value:
            return OFF
        if value == SHADOW:
            return SHADOW
        if value in _LEGACY_LIVE or value == LIVE:
            return LIVE
        raise ConfigError('RADAR_REVIEW_TIER is %r; expected one of "", '
                          '"shadow", "1"' % value)

    legacy = (environ.get('RADAR_SONNET_REVIEW') or '').strip()
    if not legacy:
        return OFF
    if legacy == SHADOW:
        return SHADOW
    if legacy in _LEGACY_LIVE:
        return LIVE
    raise ConfigError('RADAR_SONNET_REVIEW is %r; expected "shadow" or "1"'
                      % legacy)


def resolve_settings(environ=None):
    """Read the environment into an immutable decision. Constructs nothing."""
    environ = os.environ if environ is None else environ

    tone = (environ.get('RADAR_JUDGE_TONE') or '0').strip()
    if tone != '0':
        # Passing the tone criteria is evidence for a later, separately
        # reviewed promotion. It is not a switch, and a build that let one
        # be flipped would make the trial's central claim -- that encoder
        # tone never reaches a reader -- depend on an environment variable.
        raise ConfigError(
            'RADAR_JUDGE_TONE is %r; this build accepts only "0". Enabling '
            'encoder tone is a separate change, not a setting.' % tone)

    settings = Settings(primary=_spec(environ, 'RADAR_JUDGE_PRIMARY'),
                        review=_spec(environ, 'RADAR_JUDGE_REVIEW'),
                        review_mode=_review_mode(environ),
                        write_encoder_tone=False,
                        artifact_dir=(environ.get('RADAR_JUDGE_ARTIFACT_DIR')
                                      or None))
    return settings


# ---- what the passes actually use -------------------------------------------
#
# Resolved once and held for the process lifetime. A pass asks for the
# backend it should use; it does not read the environment, and it cannot
# construct one on the fly.

_active = {'primary': None, 'review': None, 'mode': OFF, 'settings': None}


def initialize_judges(settings, now=None):
    """Construct the configured backends, or fail the daemon's startup.

    The encoder is the strict case: it may only run against a trial that is
    armed for THIS artifact and prompt, because the armed row is what pins
    the evidence its recovery would need. A missing or mismatched trial is
    a startup failure. A trial already recovering or recovered is not --
    that is a normal end state, and the daemon should keep ingesting with
    judging switched off rather than refuse to run at all.
    """
    import datetime as dt

    from . import judge_backends, judge_trial

    now = now or dt.datetime.utcnow()
    primary = review = None

    if settings.primary:
        primary = judge_backends.construct_backend(
            settings.primary, artifact_dir=settings.artifact_dir)
        if getattr(primary, 'writes_tone', False) is False \
                and primary.id == judge_backends.ENCODER_MODEL_ID:
            primary = _encoder_or_none(primary, now)

    if settings.review:
        review = judge_backends.construct_backend(
            settings.review, effort='low',
            artifact_dir=settings.artifact_dir)
        if not review.supports_review:
            raise ConfigError(
                '%r cannot serve the review role: review is an INDEPENDENT '
                'second opinion, and this backend has none to give'
                % settings.review)

    _active.update(primary=primary, review=review,
                   mode=settings.review_mode, settings=settings)
    logger.info('radar judge: primary=%s review=%s mode=%r',
                primary.id if primary else DISABLED,
                review.id if review else DISABLED,
                settings.review_mode or OFF)
    return _active


def _encoder_or_none(backend, now):
    from . import judge_trial
    try:
        row = judge_trial.guard_encoder_trial(now)
    except judge_trial.TrialError as why:
        state = judge_trial.current()
        if state is not None and state.status in (judge_trial.RECOVERING,
                                                  judge_trial.RECOVERED):
            logger.warning('radar judge: the encoder is configured but its '
                           'trial is %s (%s); judging is disabled and '
                           'ingestion continues', state.status, why)
            return None
        raise ConfigError('the encoder cannot start: %s' % why)
    if row.artifact_sha256 and getattr(backend, 'bundle_sha256', None) \
            and row.artifact_sha256 != backend.bundle_sha256():
        raise ConfigError(
            'the deployed artifact does not match the armed trial '
            '(%s armed, %s deployed); replacing a file is a different trial'
            % (row.artifact_sha256[:12], backend.bundle_sha256()[:12]))
    return backend


def active_primary():
    return _active['primary']


def active_review():
    """The review backend, but only when a mode is set as well.

    Either alone judges nothing. A backend with no mode is a rollout that
    was prepared and not started; a mode with no backend is one that was
    started without a judge.
    """
    return _active['review'] if review_mode() in (SHADOW, LIVE) else None


def review_mode(environ=None):
    """The review mode, resolved from the environment on every read.

    Deliberately not cached: it is one small string, the review pass and
    the board's over-ceiling gauge both need it, and the two used to read
    RADAR_SONNET_REVIEW separately with slightly different accepted values.
    One parser, one precedence, and an unrecognised value fails loudly in
    both places instead of quietly meaning "off" in one of them.
    """
    return _review_mode(os.environ if environ is None else environ)


def reset_for_tests():
    _active.update(primary=None, review=None, mode=OFF, settings=None)
