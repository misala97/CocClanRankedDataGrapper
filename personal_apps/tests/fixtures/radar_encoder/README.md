# The encoder test artifact

A complete, valid judge artifact in the shipping layout — `active.json`
pointing at `v1/` with `model.onnx`, `tokenizer.json` and `config.json` — at
about 12 KB instead of 566 MB.

## Why a real graph and not a mock

Everything that can go wrong in `EncoderBackend` is a join between four
things that a mock would supply from one source: what the tokenizer emits,
what the graph's inputs are named, which output index is which head, and
which class list an argmax gets looked up in. A mocked session would assert
that join against itself and pass while the real one mismatched.

So this is a real ONNX graph run by the real onnxruntime and a real
`tokenizers` tokenizer, matching the shipping artifact's **shape** exactly:
three int64 inputs (`input_ids`, `attention_mask`, `token_type_ids`), five
named outputs in head order, the same five class lists, a 256-token window,
opset 17, dynamic batch axis.

## Why it has no weights

It is not a model and does not pretend to be. Each head answers

    (sum of the unpadded input ids, each plus its segment id) mod len(classes)

one-hot. Two consequences, both deliberate:

- A test computes the expected verdict for an input **itself**, from the
  tokenizer alone, so "the right verdict reached the right item" is an exact
  assertion rather than "the answers differ".
- All three inputs genuinely participate. An earlier version accepted
  `token_type_ids` and ignored it; the exporter correctly pruned the dead
  input out of the graph, which would have left a fixture unable to catch an
  adapter that forgot to send segment ids.

Random weights were tried first and were worse: on four ordinary inputs two
of them produced identical five-field verdicts, so a shuffled-batch keying
bug could have passed.

Accuracy is emphatically not tested here. The adapter's job is to feed a
graph and map its argmaxes onto head names; a fixture that also had to be
*right* would be testing the training run instead, and the training run has
its own frozen evaluation sets.

## Regenerating

Needs torch and onnx, which are **not** runtime dependencies and must not
become them — the application only ever runs a graph, which onnxruntime
does. Use the training venv:

```bash
/c/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe \
    personal_apps/tests/fixtures/radar_encoder/make_fixture.py
```

`make_fixture.py` is not imported by any test. Regenerate only when the
shipping artifact's shape changes — a new head, a changed class list, a
different window — and expect the head-mismatch tests to be what tells you
so.

The vocabulary is a small word list plus `w0`..`w31`; anything outside it
tokenizes to `[UNK]`, and two texts made only of unknown words would encode
identically, which would quietly disarm the discrimination assertions. Tests
should build their inputs from words the vocabulary contains.
