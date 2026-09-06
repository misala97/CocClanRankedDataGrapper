# personal_apps/features/radar/judge_backends.py
"""Who answers the judgment question, behind one small protocol.

`llm_sentiment` owns what the question IS -- the binding prompt, the binding
schema, the enum validation, the discard-never-default rule, the storage and
the routing. This module owns only what a particular answerer needs: an HTTP
call and a JSON parse for Anthropic, an ONNX session for the local encoder.

The split exists because exactly one function in the pipeline was ever
vendor-shaped. Everything else -- batching, token attribution, validation,
review precedence -- is about radar's semantics and stays where it was.

Two rules keep it honest:

- **Validation does not live here.** An adapter reports what its backend
  said, including a field the backend left out; `llm_sentiment.judge` decides
  what counts as a verdict. One boundary for every backend means an adapter
  bug cannot invent a valid-looking answer.
- **No fallback.** A backend that cannot answer raises SentimentUnavailable
  and its batch stays unjudged. Silently substituting another backend would
  make the stored provenance a lie.
"""
import dataclasses
import json
import logging
import os
import typing

import anthropic

from .llm_sentiment import (BATCH_SIZE, PASS_LIMIT, V2_SCHEMA, Judgment,
                            SentimentUnavailable, _FIELD_ENUMS, _prompt_v2)

logger = logging.getLogger('radar.judge_backends')


@dataclasses.dataclass(frozen=True)
class Usage:
    """What one judge_batch call consumed.

    Zero for a tokenless backend, and that zero is a fact rather than an
    absence: the encoder really does cost nothing, which is why its rate is
    an explicit 0.0 in spend.MODEL_RATES instead of a missing entry.
    """
    input_tokens: int
    output_tokens: int


class JudgeBackend(typing.Protocol):
    """What llm_sentiment needs from whoever answers."""

    id: str                 # <= 40 chars; the provenance value AND spend key
    batch_size: int         # items per judge_batch call
    pass_limit: int         # items one scheduled pass will take
    supports_review: bool   # may this backend serve the review role
    writes_tone: bool       # may its attitude reach the columns readers see

    def judge_batch(self, batch: list, *, preamble: str | None = None
                    ) -> tuple[dict[typing.Any, Judgment], Usage]:
        """Verdicts for the items it could judge, keyed by item.key.

        A key absent from the result was NOT judged and stays NULL. Raises
        SentimentUnavailable for anything that is not a verdict: a refusal,
        a transport failure, unparseable output, a wrong-shaped answer.
        Never returns a defaulted verdict -- a field the backend did not
        supply comes back as None and is discarded upstream, which is not
        the same as inventing a plausible value for it.
        """


class AnthropicBackend:
    """The existing hosted path, moved rather than rewritten.

    `effort` is a constructor argument because it is a property of the model
    being called, not of the judging: Haiku 4.5 rejects it with a 400 and the
    Sonnet review tier requires it. It used to travel as a parameter through
    two layers of generic code and be inferred from a model-id comparison at
    the reference CLI.
    """

    supports_review = True
    writes_tone = True
    # The hosted sizes, still owned by llm_sentiment: 20 per call, 400 per
    # scheduled pass. A backend with different economics carries its own.
    batch_size = BATCH_SIZE
    pass_limit = PASS_LIMIT

    def __init__(self, model, effort=None, *, client=None):
        self.id = model
        self.effort = effort
        # Lazily constructed: anthropic.Anthropic() raises without an API
        # key, and importing this module must not require one. Tests inject.
        self._client = client

    def client(self):
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def judge_batch(self, batch, *, preamble=None):
        output_config = {'format': {'type': 'json_schema', 'schema': V2_SCHEMA}}
        if self.effort is not None:
            output_config['effort'] = self.effort
        try:
            response = self.client().messages.create(
                model=self.id, max_tokens=2048, output_config=output_config,
                messages=[{'role': 'user',
                           'content': _prompt_v2(batch, preamble=preamble)}])
        except anthropic.APIError as exc:
            # Translated at the vendor boundary, so nothing upstream has to
            # know that this backend speaks HTTP.
            raise SentimentUnavailable('anthropic API error: %s' % exc)

        if getattr(response, 'stop_reason', None) == 'refusal':
            raise SentimentUnavailable('the model declined to classify this batch')
        try:
            text = next(block.text for block in response.content
                        if block.type == 'text')
            verdicts = json.loads(text)['verdicts']
        except (StopIteration, ValueError, KeyError, TypeError) as exc:
            raise SentimentUnavailable('unparseable response: %s' % exc)
        # Well-formed JSON with the wrong SHAPE ({"verdicts": {"n": 1}}) must
        # cost only this batch, exactly like malformed JSON -- iterating a
        # dict here yielded strings and an AttributeError escaped the whole
        # pass (Codex review, finding 8).
        if not isinstance(verdicts, list):
            raise SentimentUnavailable('verdicts is %s, not a list'
                                       % type(verdicts).__name__)

        got = {}
        for entry in verdicts:
            if not isinstance(entry, dict):
                continue
            number = entry.get('n')
            if not isinstance(number, int) or not 1 <= number <= len(batch):
                continue
            # Reported as given, missing fields included. Whether these
            # values are verdicts is llm_sentiment.judge's decision.
            got[batch[number - 1].key] = Judgment(
                **{field: entry.get(field) for field in _FIELD_ENUMS})

        usage = getattr(response, 'usage', None)
        return got, Usage(getattr(usage, 'input_tokens', 0) or 0,
                          getattr(usage, 'output_tokens', 0) or 0)


# ---- the local encoder ------------------------------------------------------

ENCODER_MODEL_ID = 'radar-encoder-v1'

# Measured on the VPS (onnxruntime 1.29, 2 vCPU): 7.0-7.5 rows/s at both 2
# and 4 threads -- it is memory-bandwidth bound, so the extra threads buy
# nothing. Resident stays flat at 1,081 MB for batch 1 and batch 4 and jumps
# to 1,715 MB at batch 16, which is the whole reason the batch is 4.
ENCODER_BATCH_SIZE = 4
ENCODER_PASS_LIMIT = 400
ENCODER_INTRA_OP_THREADS = 2
ENCODER_INTER_OP_THREADS = 1

# The window the shipping artifact was trained at. 512 was measured too and
# scored identically on both locked sets while doubling inference memory and
# time, so 256 is a decision, not a default.
ENCODER_MAX_LEN = 256

DEFAULT_ARTIFACT_DIR = os.path.join(os.path.dirname(__file__), '..', '..',
                                    'artifacts', 'judge')


class EncoderArtifactError(Exception):
    """The artifact on disk is not the one this code knows how to read."""


class EncoderBackend:
    """The distilled encoder: five heads over one shared encoder, local.

    Validated at CONSTRUCTION, loaded on first use. The daemon resolves its
    configuration at startup, so an artifact that does not match this code
    must fail there -- loudly, before any judging -- rather than at the
    first scheduled pass. The ONNX session is a different matter: it is
    ~1 GB resident and belongs to the process that actually judges, so it
    is built on the first batch and then held for the process lifetime.

    A load failure is LATCHED. It raises SentimentUnavailable for the rest
    of the adapter's life without retrying, and it never falls back to
    another backend: judging with a different judge than the one recorded
    would make the stored provenance a lie.
    """

    supports_review = False       # it has no independent second opinion to give
    # Its relevance and content_origin verdicts take effect -- they are what
    # the evidence supports -- but its attitude never reaches a column any
    # reader sees. Tone is the one field a post card shows, the encoder
    # reversed polarity on 3 of 54 directional rows where Haiku reversed
    # none, and the trial's own gates deliberately do not test attitude. It
    # is judged and stored in history for evaluation, and is absent from
    # production by construction rather than by a display rule.
    writes_tone = False
    batch_size = ENCODER_BATCH_SIZE
    pass_limit = ENCODER_PASS_LIMIT

    def __init__(self, artifact_dir=None):
        self.id = ENCODER_MODEL_ID
        self.artifact_dir = os.path.abspath(artifact_dir or DEFAULT_ARTIFACT_DIR)
        self.model_path, self.tokenizer_path, self.config = self._validate()
        self.max_len = self.config['max_len']
        self.heads = self.config['heads']
        self._session = None
        self._tokenizer = None
        self._load_error = None

    def bundle_sha256(self):
        """SHA256 over the three artifact files, in a fixed order.

        The identity of a DEPLOYED artifact, checked against the one the
        trial was armed for. Not stored inside config.json, which would
        make the hash cover itself; and computed over all three files
        because swapping the tokenizer alone changes every verdict while
        leaving the weights untouched.
        """
        import hashlib
        digest = hashlib.sha256()
        version_dir = os.path.dirname(self.model_path)
        for name in ('model.onnx', 'tokenizer.json', 'config.json'):
            path = os.path.join(version_dir, name)
            file_digest = hashlib.sha256()
            with open(path, 'rb') as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b''):
                    file_digest.update(chunk)
            line = '%s=%s\n' % (name, file_digest.hexdigest())
            digest.update(line.encode('utf-8'))
        return digest.hexdigest()

    # -- construction-time checks -------------------------------------------

    def _read_json(self, path, what):
        if not os.path.isfile(path):
            raise EncoderArtifactError('%s: no %s' % (path, what))
        try:
            with open(path, encoding='utf-8') as handle:
                return json.load(handle)
        except ValueError as exc:
            raise EncoderArtifactError('%s is not readable JSON: %s'
                                       % (path, exc))

    def _validate(self):
        pointer = self._read_json(os.path.join(self.artifact_dir, 'active.json'),
                                  'active.json pointer')
        if pointer.get('id') != ENCODER_MODEL_ID:
            raise EncoderArtifactError(
                'active.json names id %r, this build serves %r'
                % (pointer.get('id'), ENCODER_MODEL_ID))
        path = pointer.get('path')
        if not path:
            raise EncoderArtifactError('active.json names no path')
        version_dir = os.path.join(self.artifact_dir, path)

        config = self._read_json(os.path.join(version_dir, 'config.json'),
                                 'config.json')
        model_path = os.path.join(version_dir, 'model.onnx')
        tokenizer_path = os.path.join(version_dir, 'tokenizer.json')
        for candidate, what in ((model_path, 'model.onnx'),
                                (tokenizer_path, 'tokenizer.json')):
            if not os.path.isfile(candidate):
                raise EncoderArtifactError('%s: no %s' % (version_dir, what))

        if config.get('max_len') != ENCODER_MAX_LEN:
            raise EncoderArtifactError(
                'artifact max_len is %r, this build reads %d tokens'
                % (config.get('max_len'), ENCODER_MAX_LEN))

        heads = config.get('heads')
        if not isinstance(heads, dict):
            raise EncoderArtifactError('config.json has no heads mapping')
        # Both the SET of heads and the ORDER of each class list matter: the
        # class list is what an argmax index is looked up in, so a reordered
        # list silently relabels every verdict. Compared as tuples because
        # JSON gives lists and _FIELD_ENUMS holds tuples.
        missing = sorted(set(_FIELD_ENUMS) - set(heads))
        extra = sorted(set(heads) - set(_FIELD_ENUMS))
        if missing or extra:
            raise EncoderArtifactError(
                'artifact heads do not match this build: missing %s, unexpected %s'
                % (missing or 'none', extra or 'none'))
        for field, allowed in _FIELD_ENUMS.items():
            if tuple(heads[field]) != tuple(allowed):
                raise EncoderArtifactError(
                    "artifact head %r has classes %s, this build expects %s"
                    % (field, list(heads[field]), list(allowed)))
        return model_path, tokenizer_path, config

    # -- lazy session --------------------------------------------------------

    def _unavailable(self):
        """The latched failure, marked so it is reported once, not per batch.

        An Anthropic batch failure is news every time -- it is usually
        transient. A missing or corrupt artifact is one fact, and repeating
        it every ten minutes forever buries the log it belongs in.
        """
        error = SentimentUnavailable('encoder artifact unusable: %s'
                                     % self._load_error)
        error.already_reported = True
        return error

    def _load(self):
        if self._load_error is not None:
            raise self._unavailable()
        if self._session is None:
            try:
                import numpy
                import onnxruntime
                from tokenizers import Tokenizer

                options = onnxruntime.SessionOptions()
                options.intra_op_num_threads = ENCODER_INTRA_OP_THREADS
                options.inter_op_num_threads = ENCODER_INTER_OP_THREADS
                session = onnxruntime.InferenceSession(
                    self.model_path, options,
                    providers=['CPUExecutionProvider'])
                tokenizer = Tokenizer.from_file(self.tokenizer_path)
                tokenizer.enable_truncation(self.max_len)
                tokenizer.enable_padding(length=self.max_len)
            except Exception as exc:          # noqa: BLE001 -- latched below
                self._load_error = '%s: %s' % (type(exc).__name__, exc)
                logger.error('radar encoder judge is unavailable: %s (%s); '
                             'this backend will not retry',
                             self._load_error, self.model_path)
                raise self._unavailable()
            self._numpy = numpy
            self._session = session
            self._tokenizer = tokenizer
            self._inputs = {value.name for value in session.get_inputs()}
            self._outputs = [value.name for value in session.get_outputs()]
        return self._session, self._tokenizer

    # -- judging -------------------------------------------------------------

    def judge_batch(self, batch, *, preamble=None):
        """The five fields for each item, straight from the heads.

        `preamble` is accepted and unused: it exists to tell a hosted model
        it is reviewing independently, and this backend does not read a
        prompt at all. PROMPT_VERSION still describes the label semantics
        it answers to; the stored backend id records that it answered.
        """
        session, tokenizer = self._load()
        numpy = self._numpy
        encoded = tokenizer.encode_batch(
            [(item.prepared.target_ticker, item.prepared.author_text)
             for item in batch])
        feed = {'input_ids': numpy.array([e.ids for e in encoded],
                                         dtype=numpy.int64),
                'attention_mask': numpy.array([e.attention_mask for e in encoded],
                                              dtype=numpy.int64)}
        if 'token_type_ids' in self._inputs:
            feed['token_type_ids'] = numpy.array([e.type_ids for e in encoded],
                                                 dtype=numpy.int64)
        try:
            outputs = session.run(None, feed)
        except Exception as exc:              # noqa: BLE001
            raise SentimentUnavailable('encoder inference failed: %s' % exc)

        by_head = {name: outputs[index].argmax(-1)
                   for index, name in enumerate(self._outputs)}
        got = {}
        for position, item in enumerate(batch):
            got[item.key] = Judgment(
                **{field: self.heads[field][int(by_head[field][position])]
                   for field in _FIELD_ENUMS})
        return got, Usage(0, 0)


# ---- registry --------------------------------------------------------------
#
# Parsing an environment variable is deliberately NOT here: construction is
# explicit, and the daemon resolves its configuration once at startup (spec
# §2.3, built in a later task). A web request that imports this module must
# not be able to open a client or a model session as a side effect.

_ANTHROPIC_PREFIX = 'anthropic:'


def construct_backend(spec, *, effort=None, artifact_dir=None):
    """Build the backend a spec string names.

    'anthropic:<model>' and 'encoder' are the accepted forms. An unknown
    spec is an error rather than a silent fallback to a default judge:
    judging with the wrong backend is worse than not judging, because the
    wrong answers are stored and counted under the wrong provenance.
    """
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError('judge backend spec must be a non-empty string')
    spec = spec.strip()
    if spec == 'encoder':
        return EncoderBackend(artifact_dir)
    if spec.startswith(_ANTHROPIC_PREFIX):
        model = spec[len(_ANTHROPIC_PREFIX):].strip()
        if not model:
            raise ValueError('anthropic backend spec names no model: %r' % spec)
        return AnthropicBackend(model, effort=effort)
    raise ValueError('unknown judge backend spec: %r' % spec)


def writes_tone(backend):
    """Whether this backend's tone may be materialized.

    Read off the backend rather than defaulted, and with no fallback: a new
    backend that forgets to declare a tone policy must fail here, not
    quietly acquire the permissive one and start writing what readers see.
    """
    try:
        return bool(backend.writes_tone)
    except AttributeError:
        raise ValueError('backend %r declares no tone policy'
                         % getattr(backend, 'id', backend))


def writes_tone_for_model(model_id):
    """The same question about a STORED id, for rows already on disk.

    PURE -- it constructs nothing. Review routing needs it to decide
    whether a mention's own tone columns belong to the same judgment as its
    relevance columns, which is false for anything the encoder wrote during
    a suppressed-tone trial.
    """
    return model_id != ENCODER_MODEL_ID


def backend_label(model_id):
    """A display name for whoever produced a stored judgment.

    PURE. It reads a recorded id and returns a word; it opens no client, no
    session and no file, because the post-card payload is built inside a web
    request. An id this build does not recognise -- a retired model, a future
    backend -- is 'model', which is true of all of them and claims nothing
    further.
    """
    if isinstance(model_id, str) and model_id.startswith('claude-'):
        return 'Claude'
    return 'model'
