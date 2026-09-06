"""Build the tiny encoder artifact the adapter tests load.

Run it with an environment that has torch and onnx -- the training venv,
NOT the application venv:

    /c/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe \
        personal_apps/tests/fixtures/radar_encoder/make_fixture.py

Neither torch nor onnx is a runtime dependency and neither should become
one: the application only ever RUNS a graph, which onnxruntime does. This
script exists so the fixture is reproducible rather than a mystery binary,
and it is not imported by any test.

The fixture mirrors the shipping artifact's SHAPE exactly -- three int64
inputs, five named outputs, the same class lists, the same 256-token
window, opset 17 -- and nothing else about it. It has no weights at all;
each head is a fixed arithmetic function of the input ids (see
TinyEncoder). That is the point: the adapter's job is to feed a graph and
map its argmaxes onto head names, and a test that proved the model was ALSO
accurate would be testing the training run instead.
"""
import json
import os

import torch
from tokenizers import Tokenizer, models, pre_tokenizers, processors

HERE = os.path.dirname(os.path.abspath(__file__))
ARTIFACT = os.path.join(HERE, 'v1')

# The five heads and their class lists, in the order the real artifact
# records them. The adapter checks these against llm_sentiment._FIELD_ENUMS
# and refuses to load if they disagree, so they are copied here literally
# rather than imported -- a fixture that imports the thing it is testing
# against cannot catch a change to it.
HEADS = {
    'relevance': ['relevant', 'irrelevant', 'uncertain'],
    'content_origin': ['human_chatter', 'broadcast_or_automated', 'uncertain'],
    'attitude': ['positive', 'negative', 'mixed', 'none'],
    'expected_move': ['up', 'down', 'flat', 'unknown'],
    'confidence': ['high', 'medium', 'low'],
}
MAX_LEN = 256
VOCAB_SIZE = 64

# Enough real words that a test can write plausible text, plus w0..w31 for
# tests that just need inputs which differ. Everything else is [UNK], and
# two texts made only of [UNK] would tokenize identically -- which would
# quietly disarm the shuffled-batch test.
WORDS = ['great', 'terrible', 'buying', 'selling', 'calls', 'puts', 'earnings',
         'the', 'a', 'is', 'not', 'up', 'down', 'zza', 'zzb', 'zzc', 'zzd']


def build_tokenizer():
    vocab = {'[PAD]': 0, '[UNK]': 1, '[CLS]': 2, '[SEP]': 3}
    for word in WORDS:
        vocab[word] = len(vocab)
    for n in range(32):
        vocab['w%d' % n] = len(vocab)
    assert len(vocab) <= VOCAB_SIZE, len(vocab)

    tokenizer = Tokenizer(models.WordLevel(vocab=vocab, unk_token='[UNK]'))
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    # A PAIR tokenizer: the judge asks about (ticker, post), and the second
    # segment carries type id 1 exactly as the real DeBERTa artifact does.
    tokenizer.post_processor = processors.TemplateProcessing(
        single='[CLS] $A [SEP]',
        pair='[CLS] $A [SEP] $B:1 [SEP]:1',
        special_tokens=[('[CLS]', 2), ('[SEP]', 3)])
    return tokenizer


class TinyEncoder(torch.nn.Module):
    """A deterministic function of the input, not a trained model.

    Each head answers `(sum of the unpadded input ids) mod len(classes)`,
    one-hot. Random weights were the obvious thing and were worse: two
    different inputs landed on the same five verdicts often enough that a
    shuffled-batch test could pass while the adapter mismatched keys.

    This way a test computes the expected verdict for an input itself, from
    the tokenizer alone, so "the right answer reached the right key" is an
    exact assertion rather than "the answers differ".
    """

    def forward(self, input_ids, attention_mask, token_type_ids):
        # All three inputs really participate. An earlier version accepted
        # token_type_ids and ignored it, and the exporter -- correctly --
        # pruned the dead input out of the graph, leaving a fixture that
        # could not catch an adapter which forgot to send segment ids.
        total = ((input_ids + token_type_ids) * attention_mask).sum(dim=1,
                                                                    keepdim=True)
        out = []
        for classes in HEADS.values():
            positions = torch.arange(len(classes)).unsqueeze(0)
            out.append((total % len(classes) == positions).to(torch.float32))
        return tuple(out)


def main():
    os.makedirs(ARTIFACT, exist_ok=True)

    build_tokenizer().save(os.path.join(ARTIFACT, 'tokenizer.json'))

    model = TinyEncoder().eval()
    example = (torch.zeros(1, MAX_LEN, dtype=torch.int64),
               torch.ones(1, MAX_LEN, dtype=torch.int64),
               torch.zeros(1, MAX_LEN, dtype=torch.int64))
    names = ['input_ids', 'attention_mask', 'token_type_ids']
    with torch.no_grad():
        torch.onnx.export(
            model, example, os.path.join(ARTIFACT, 'model.onnx'),
            input_names=names, output_names=list(HEADS),
            dynamic_axes={name: {0: 'batch'} for name in names + list(HEADS)},
            opset_version=17, dynamo=False)

    with open(os.path.join(ARTIFACT, 'config.json'), 'w', encoding='utf-8') as out:
        json.dump({'base': 'tests/fixtures/radar_encoder (not a real model)',
                   'heads': HEADS, 'max_len': MAX_LEN,
                   'manifest': {'fixture': True,
                                'generated_by': 'make_fixture.py'}},
                  out, indent=1)
    with open(os.path.join(HERE, 'active.json'), 'w', encoding='utf-8') as out:
        json.dump({'path': 'v1/', 'id': 'radar-encoder-v1'}, out, indent=1)

    size = os.path.getsize(os.path.join(ARTIFACT, 'model.onnx'))
    print('wrote %s (model.onnx %.1f KB)' % (ARTIFACT, size / 1024))


if __name__ == '__main__':
    main()
