# personal_apps/features/radar/sentiment.py
"""The local sentiment arm: promoted classifier artifact, lexicon fallback.

score() is what ingest calls per (post, ticker). When a trained classifier
artifact has passed its promotion gates (spec 2026-08-31 §8/§10.3) and is
pointed to by active.json, it scores; otherwise the hand lexicon below
does. Falling back to the lexicon -- never to a silent 0.0 -- is the
cold-start behavior the spec demands (§5.1): an unreadable, stale, or
missing artifact must not turn every local score into fake silence.

The lexicon is knowingly weak on sarcasm and inverted positions; the
model judgment outranks both scorers wherever it exists, and the
local-vs-model disagreement is the review signal.
"""
import logging
import os
import re

logger = logging.getLogger('radar.sentiment')

_WORD_RE = re.compile(r"[a-z']+")

_POSITIVE = {
    'bullish': 2.0, 'buy': 1.0, 'long': 0.5, 'calls': 1.0, 'moon': 1.5,
    'squeeze': 1.0, 'rip': 1.0, 'ripping': 1.5, 'great': 1.0, 'huge': 1.0,
    'upside': 1.5, 'undervalued': 1.5, 'beat': 1.0, 'strong': 1.0,
    'rally': 1.0, 'breakout': 1.5, 'green': 0.5, 'gains': 1.0, 'win': 1.0,
}

_NEGATIVE = {
    'bearish': 2.0, 'sell': 1.0, 'short': 0.5, 'puts': 1.0, 'crash': 1.5,
    'dump': 1.5, 'dumps': 1.5, 'dumping': 1.5, 'terrible': 1.5, 'bad': 1.0,
    'overvalued': 1.5, 'miss': 1.0, 'missed': 1.0, 'weak': 1.0, 'bag': 1.0,
    'bagholder': 1.5, 'red': 0.5, 'losses': 1.0, 'rug': 1.5, 'scam': 2.0,
}

_NEGATIONS = {'not', 'no', 'never', "isn't", "aint", "ain't", "doesn't", "don't"}

# How many tokens after a negation stay flipped.
_NEGATION_SCOPE = 3

# Divisor turning a raw sum into roughly [-1, 1] before clamping. Four strong
# words in one direction is already a maximally one-sided post.
_SCALE = 8.0


LEXICON_VERSION = 'lexicon-v1'

# Artifact location: git-ignored directory in the checkout by default
# (there is no Flask instance/ folder in this repo), overridable for
# tests and unusual layouts. active.json holds {'version', 'path'};
# promotion replaces it atomically (os.replace), so rollback is
# restoring the previous pointer -- no rescoring machinery involved.
ARTIFACT_DIR = os.getenv(
    'RADAR_SENTIMENT_ARTIFACT_DIR',
    os.path.join(os.path.dirname(__file__), '..', '..', 'artifacts',
                 'radar_sentiment'))

_active_cache = {'pointer_mtime': None, 'artifact': None, 'warned': False}


def _pointer_path():
    return os.path.join(ARTIFACT_DIR, 'active.json')


def _load_active():
    """The promoted artifact dict, or None. Cached per pointer mtime.

    Never raises: any problem -- missing pointer, unreadable file, a
    preparation_version or sklearn line this code does not match -- logs
    once and falls back to the lexicon (spec §5.1).
    """
    import json
    pointer = _pointer_path()
    try:
        mtime = os.path.getmtime(pointer)
    except OSError:
        _active_cache.update(pointer_mtime=None, artifact=None)
        return None
    if _active_cache['pointer_mtime'] == mtime:
        return _active_cache['artifact']

    artifact = None
    try:
        import joblib
        import sklearn
        with open(pointer, encoding='utf-8') as handle:
            meta = json.load(handle)
        path = meta['path']
        if not os.path.isabs(path):
            path = os.path.join(ARTIFACT_DIR, path)
        candidate = joblib.load(path)
        from . import sentiment_input
        prep = candidate.get('preparation_version')
        wanted = sentiment_input.PREPARATION_VERSION
        trained_sklearn = str(candidate.get('sklearn_version', ''))
        running = '.'.join(sklearn.__version__.split('.')[:2])
        if prep != wanted:
            raise ValueError('artifact preparation_version %r, code wants %r'
                             % (prep, wanted))
        if '.'.join(trained_sklearn.split('.')[:2]) != running:
            raise ValueError('artifact sklearn %s, running %s'
                             % (trained_sklearn, sklearn.__version__))
        # Loadable is not usable: a joblib file missing a runtime key
        # raised KeyError INSIDE ingest before this check existed (Codex
        # final review, blocker 4).
        missing = [key for key in ('version', 'word_vec', 'char_vec',
                                   'clf', 'tau', 'classes')
                   if key not in candidate]
        if missing:
            raise ValueError('artifact missing keys: %s'
                             % ', '.join(missing))
        artifact = candidate
    except Exception as exc:
        if not _active_cache['warned']:
            logger.warning('radar sentiment artifact unusable (%s) -- '
                           'falling back to the lexicon', exc)
            _active_cache['warned'] = True
    _active_cache.update(pointer_mtime=mtime, artifact=artifact)
    return artifact


def _known_tickers():
    from . import universe
    return set(universe.load_lookup().keys())


def classifier_text(prepared):
    """The exact feature text the trainer and the scorer share."""
    from . import sentiment_input
    masked = sentiment_input.mask_tickers(
        prepared.author_text, prepared.target_ticker, _known_tickers())
    return 'TICKER=%s %s' % (prepared.target_ticker, masked)


def _classifier_score(artifact, prepared):
    from scipy.sparse import hstack
    text = classifier_text(prepared)
    features = hstack([artifact['word_vec'].transform([text]),
                       artifact['char_vec'].transform([text])])
    proba = dict(zip(artifact['clf'].classes_,
                     artifact['clf'].predict_proba(features)[0]))
    p_pos = float(proba.get('positive', 0.0))
    p_neg = float(proba.get('negative', 0.0))
    top = max(p_pos, p_neg)
    if top < artifact['tau'] or top <= (1.0 - p_pos - p_neg):
        return 0.0
    return p_pos - p_neg


def active_version():
    """Which local scorer is live: the artifact's version, or the lexicon.

    Defensive .get on top of the load-time key validation -- this runs
    inside ingest's write path and must never raise.
    """
    artifact = _load_active()
    if artifact is not None:
        return artifact.get('version') or LEXICON_VERSION
    return LEXICON_VERSION


def score(prepared):
    """The local sentiment float for one prepared (post, ticker) input.

    [-1, 1]; 0.0 means no signal. Provisional by design: it covers the
    minutes before the LLM verdict and the tiers the LLM never reads.
    Takes a sentiment_input.PreparedInput so cleaning (HTML entities,
    reddit parent-title stripping) can never diverge from what the LLM
    judge and the trainer see.
    """
    artifact = _load_active()
    if artifact is not None:
        try:
            return _classifier_score(artifact, prepared)
        except Exception as exc:
            # A LOADABLE artifact can still be broken -- a missing key, a
            # transformer that raises. Ingest must never die for the local
            # score: disable the artifact for this process and fall back
            # (Codex review, finding 8).
            logger.warning('radar sentiment artifact failed at scoring '
                           '(%s) -- falling back to the lexicon', exc)
            _active_cache.update(artifact=None)
    return lexicon_score(prepared.author_text)


def lexicon_score(text):
    """A sentiment score in [-1.0, 1.0]. 0.0 means no lexicon words matched."""
    tokens = _WORD_RE.findall((text or '').lower())
    total = 0.0
    negated_until = -1

    for index, token in enumerate(tokens):
        if token in _NEGATIONS:
            negated_until = index + _NEGATION_SCOPE
            continue

        weight = _POSITIVE.get(token, 0.0) - _NEGATIVE.get(token, 0.0)
        if weight == 0.0:
            continue
        if index <= negated_until:
            weight = -weight
        total += weight

    return max(-1.0, min(1.0, total / _SCALE))
