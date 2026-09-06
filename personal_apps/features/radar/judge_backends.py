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


# ---- registry --------------------------------------------------------------
#
# Parsing an environment variable is deliberately NOT here: construction is
# explicit, and the daemon resolves its configuration once at startup (spec
# §2.3, built in a later task). A web request that imports this module must
# not be able to open a client or a model session as a side effect.

_ANTHROPIC_PREFIX = 'anthropic:'


def construct_backend(spec, *, effort=None, artifact_dir=None):
    """Build the backend a spec string names.

    'anthropic:<model>' is the only accepted form today. An unknown spec is
    an error rather than a silent fallback to a default judge: judging with
    the wrong backend is worse than not judging, because the wrong answers
    are stored and counted under the wrong provenance.
    """
    if not isinstance(spec, str) or not spec.strip():
        raise ValueError('judge backend spec must be a non-empty string')
    spec = spec.strip()
    if spec.startswith(_ANTHROPIC_PREFIX):
        model = spec[len(_ANTHROPIC_PREFIX):].strip()
        if not model:
            raise ValueError('anthropic backend spec names no model: %r' % spec)
        return AnthropicBackend(model, effort=effort)
    raise ValueError('unknown judge backend spec: %r' % spec)


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
