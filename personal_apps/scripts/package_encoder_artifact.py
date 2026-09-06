#!/usr/bin/env python
"""Package a trained encoder into the artifact layout the daemon loads.

Run it with the TRAINING environment, not the application venv:

    /c/Users/michi/Desktop/radar_encoder_venv/Scripts/python.exe \
        personal_apps/scripts/package_encoder_artifact.py \
        --model C:/Users/michi/Desktop/radar_labels/encoder/model-train13000 \
        --out   personal_apps/artifacts/judge

torch and onnx are needed here and are deliberately NOT runtime
dependencies: the application only ever RUNS a graph, which onnxruntime
does in about 50 MB. This script is never imported by the app and never
runs on the server.

It differs from `scratchpad/label_export/export_onnx.py`, which was
exploratory, in three ways that matter:

- **FP32 only.** That script also writes an INT8 `model.onnx`, and the
  plain name is a trap: INT8 was measured and rejected (relevance
  0.848 -> 0.692, removal precision 0.861 -> 0.750). Nothing here produces
  a file that could be copied to the server by mistake.
- **The shipping layout**, `active.json` + `v1/`, which is what
  EncoderBackend validates at construction.
- **The manifest travels with the model.** The training run's record --
  seed, row counts, exclusions, input hashes, git HEAD -- is copied into
  the artifact's config.json, so a model on a server can still say what it
  was trained on.

It prints the bundle SHA256 at the end. That is the trial's identity: arm
with it, and startup refuses to judge if the deployed files disagree.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

OPSET = 17

# Copied literally rather than imported: this script runs in a different
# environment from the application, and an artifact whose head order came
# from the same place the check does could not catch a change to it.
# EncoderBackend refuses to load an artifact whose heads disagree with
# llm_sentiment._FIELD_ENUMS, naming the key that differs.
HEADS = {
    'relevance': ['relevant', 'irrelevant', 'uncertain'],
    'content_origin': ['human_chatter', 'broadcast_or_automated', 'uncertain'],
    'attitude': ['positive', 'negative', 'mixed', 'none'],
    'expected_move': ['up', 'down', 'flat', 'unknown'],
    'confidence': ['high', 'medium', 'low'],
}
MAX_LEN = 256
MODEL_ID = 'radar-encoder-v1'


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def bundle_sha256(version_dir):
    """The three files in a fixed order -- the same rule EncoderBackend uses.

    Over all three because swapping the tokenizer alone changes every
    verdict while leaving the weights untouched, and not stored inside
    config.json because that would make the hash cover itself.
    """
    digest = hashlib.sha256()
    for name in ('model.onnx', 'tokenizer.json', 'config.json'):
        line = '%s=%s\n' % (name, file_sha256(os.path.join(version_dir, name)))
        digest.update(line.encode('utf-8'))
    return digest.hexdigest()


def git_head():
    try:
        return subprocess.check_output(
            ['git', 'rev-parse', '--short', 'HEAD'],
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True,
                        help='training output directory holding weights.pt '
                             'and its config.json')
    parser.add_argument('--out', required=True,
                        help='artifact root; active.json and v1/ go here')
    parser.add_argument('--base', default='microsoft/deberta-v3-small')
    parser.add_argument(
        '--trainer',
        default='C:/Users/michi/Desktop/CodingStuff/personal_apps/'
                'scratchpad/label_export',
        help='directory holding train_encoder.py; the model class is '
             'imported from there so it cannot drift from the weights')
    args = parser.parse_args()

    import torch
    from transformers import AutoTokenizer

    # The model class comes from the TRAINING script, never from a copy
    # here. The weights were produced by that definition -- including a
    # dropout layer that contributes no parameters and would therefore load
    # silently against a slightly different architecture. HEADS below is
    # then a CHECK on what was imported, not a second source of truth.
    sys.path.insert(0, args.trainer)
    from train_encoder import MultiHead, HEADS as TRAINED_HEADS  # noqa: E402
    if {k: list(v) for k, v in TRAINED_HEADS.items()} != HEADS:
        raise SystemExit('the training script defines different heads (%r) '
                         'from the ones this build reads' % (TRAINED_HEADS,))

    training = json.load(open(os.path.join(args.model, 'config.json'),
                              encoding='utf-8'))
    if training.get('max_len') != MAX_LEN:
        raise SystemExit('the trained model uses max_len %r; this build reads '
                         '%d tokens' % (training.get('max_len'), MAX_LEN))
    for field, classes in HEADS.items():
        if list(training.get('heads', {}).get(field, [])) != classes:
            raise SystemExit(
                'head %r was trained as %r and this build expects %r; an '
                'argmax index means a different class in each'
                % (field, training.get('heads', {}).get(field), classes))

    version_dir = os.path.join(args.out, 'v1')
    os.makedirs(version_dir, exist_ok=True)

    class Wrapped(torch.nn.Module):
        """One output tensor per head, in a fixed order, for a clean graph.

        The trained model returns a dict; ONNX wants positional outputs,
        and the ORDER here is what `output_names` names. Getting it wrong
        would relabel every verdict without failing anything.
        """

        def __init__(self, model):
            super().__init__()
            self.model = model
            self.order = list(HEADS)

        def forward(self, input_ids, attention_mask, token_type_ids):
            out = self.model(input_ids=input_ids,
                             attention_mask=attention_mask,
                             token_type_ids=token_type_ids)
            return tuple(out[name] for name in self.order)

    model = MultiHead(args.base)
    state = torch.load(os.path.join(args.model, 'weights.pt'),
                       map_location='cpu')
    model.load_state_dict(state)
    model.eval()

    tokenizer = AutoTokenizer.from_pretrained(args.base)
    example = tokenizer('AAPL', 'placeholder text', truncation=True,
                        max_length=MAX_LEN, padding='max_length',
                        return_tensors='pt')
    names = ['input_ids', 'attention_mask', 'token_type_ids']
    inputs = (example['input_ids'], example['attention_mask'],
              example.get('token_type_ids',
                          torch.zeros_like(example['input_ids'])))

    model_path = os.path.join(version_dir, 'model.onnx')
    with torch.no_grad():
        torch.onnx.export(
            Wrapped(model), inputs, model_path, input_names=names,
            output_names=list(HEADS),
            dynamic_axes={name: {0: 'batch'}
                          for name in names + list(HEADS)},
            opset_version=OPSET, dynamo=False)

    # The fast tokenizer's own file, which is what `tokenizers` reads. Saved
    # to a temporary directory first because save_pretrained writes several
    # files and only this one ships.
    staging = os.path.join(args.out, '_tokenizer')
    tokenizer.save_pretrained(staging)
    shutil.copyfile(os.path.join(staging, 'tokenizer.json'),
                    os.path.join(version_dir, 'tokenizer.json'))
    shutil.rmtree(staging, ignore_errors=True)

    manifest = dict(training.get('manifest') or {})
    manifest.update({'opset': OPSET, 'source_model':
                     os.path.basename(os.path.normpath(args.model)),
                     'packaged_by': 'scripts/package_encoder_artifact.py',
                     'packaged_at_git_head': git_head(),
                     'precision': 'fp32'})
    with open(os.path.join(version_dir, 'config.json'), 'w',
              encoding='utf-8') as out:
        json.dump({'base': args.base, 'heads': HEADS, 'max_len': MAX_LEN,
                   'manifest': manifest}, out, indent=1)
    with open(os.path.join(args.out, 'active.json'), 'w',
              encoding='utf-8') as out:
        json.dump({'path': 'v1/', 'id': MODEL_ID}, out, indent=1)

    size = os.path.getsize(model_path) / 1e6
    print('wrote %s (%.1f MB, fp32, opset %d)' % (version_dir, size, OPSET))
    if size < 400:
        print('WARNING: an fp32 DeBERTa-v3-small export is ~566 MB. This '
              'looks like a quantized file.', file=sys.stderr)
    print()
    print('bundle sha256: %s' % bundle_sha256(version_dir))
    print()
    print('Arm the trial with that hash. Startup refuses to judge if the '
          'deployed files disagree with it.')


if __name__ == '__main__':
    main()
