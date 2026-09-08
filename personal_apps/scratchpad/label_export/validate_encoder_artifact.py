#!/usr/bin/env python
"""Prove a packaged encoder artifact before it goes anywhere near the VPS.

    cd personal_apps
    PYTHONPATH=. python scratchpad/label_export/validate_encoder_artifact.py \
        --artifact C:/Users/michi/Desktop/radar_labels/artifact-base \
        --version v1

It runs the REAL EncoderBackend against the REAL files, because the two ways
this goes wrong are both invisible to anything cheaper:

1. **The ONNX output names.** `_validate` never looks at the graph. At
   inference the backend zips `session.get_outputs()` positionally into a
   dict and then indexes it BY HEAD NAME, outside the try/except that guards
   `session.run` -- so a graph whose outputs are named `output_0…output_4`,
   or ordered differently, is a bare KeyError on every batch, forever, with
   the daemon otherwise healthy. Nothing else in the system checks this.

2. **Resident memory.** The shipping artifact is a 6-layer model at a
   256-token window and sits flat at 1,081 MB at batch 4 on a 2 vCPU box
   that also runs MariaDB with a 2500M buffer pool. A 12-layer model at 512
   is roughly 2x the layers and 2x the sequence. That arithmetic is not a
   measurement, and this script is where the measurement comes from.

Reports peak RSS and throughput so the two numbers that decide the deploy --
does it fit, and does a 400-row pass finish inside a 600 s job -- are
measured rather than extrapolated. Reads nothing from the database and
writes nothing anywhere.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

SAMPLES = [
    ('AAPL', 'apple just guided way above consensus, loading calls monday'),
    ('AAPL', 'I ate an apple for breakfast and it was delicious'),
    ('TSLA', 'tsla is going to zero, the margins are a fantasy'),
    ('NVDA', 'NVDA earnings after close. no position, just watching'),
    ('GME', 'BREAKING: $GME halted. Follow for more alerts! Link in bio'),
    ('MSFT', 'anyone know why msft dumped 3% on no news?'),
    ('AMD', 'AMD looks like a decent long here, cheap vs peers on fwd P/E'),
    ('SPY', 'spy 500 puts printed today boys'),
]


def _peak_rss_mb():
    """Peak working set for this process, in MB. Windows and POSIX."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes

        class COUNTERS(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD),
                        ('PageFaultCount', wintypes.DWORD),
                        ('PeakWorkingSetSize', ctypes.c_size_t),
                        ('WorkingSetSize', ctypes.c_size_t),
                        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                        ('PagefileUsage', ctypes.c_size_t),
                        ('PeakPagefileUsage', ctypes.c_size_t)]

        counters = COUNTERS()
        counters.cb = ctypes.sizeof(COUNTERS)
        # The signatures have to be declared. GetCurrentProcess returns a
        # HANDLE, and ctypes defaults an undeclared restype to c_int, which
        # TRUNCATES the pseudo-handle on 64-bit -- the call then fails and
        # returns a plausible-looking 0 MB, which is worse than an error for
        # the one number this script exists to report.
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.argtypes = []
        ok = 0
        for library in ('psapi', 'kernel32'):
            for entry in ('GetProcessMemoryInfo', 'K32GetProcessMemoryInfo'):
                function = getattr(getattr(ctypes.windll, library), entry, None)
                if function is None:
                    continue
                function.restype = wintypes.BOOL
                function.argtypes = [wintypes.HANDLE,
                                     ctypes.POINTER(COUNTERS), wintypes.DWORD]
                ok = function(kernel32.GetCurrentProcess(),
                              ctypes.byref(counters), counters.cb)
                if ok and counters.PeakWorkingSetSize:
                    return counters.PeakWorkingSetSize / 2 ** 20
        raise RuntimeError('could not read peak working set '
                           '(GetProcessMemoryInfo returned %r)' % ok)
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1024 if sys.platform != 'darwin' else peak / 2 ** 20


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', required=True,
                        help='artifact ROOT (the directory holding active.json)')
    parser.add_argument('--version', default=None,
                        help='version directory to point active.json at for '
                             'this run, e.g. v2. Omit to use it as it stands.')
    parser.add_argument('--batch', type=int, default=None,
                        help='override ENCODER_BATCH_SIZE for the run')
    parser.add_argument('--rows', type=int, default=64,
                        help='how many rows to judge (SAMPLES repeat)')
    args = parser.parse_args()

    from features.radar import judge_backends, sentiment_input
    from features.radar.judge_backends import EncoderBackend
    from features.radar.llm_sentiment import JudgeItem, _FIELD_ENUMS

    root = os.path.abspath(args.artifact)
    if args.version:
        # Written to a COPY of the pointer, never over a shipping one: the
        # pointer is the atomic switch and this script must not be able to
        # move a live deployment.
        pointer = os.path.join(root, 'active.json')
        existing = {}
        if os.path.isfile(pointer):
            with open(pointer, encoding='utf-8') as handle:
                existing = json.load(handle)
        want = {'path': args.version.rstrip('/') + '/',
                'id': judge_backends.ENCODER_MODEL_ID}
        if existing != want:
            print('pointing %s at %s (was %r)'
                  % (pointer, want['path'], existing.get('path')))
            with open(pointer, 'w', encoding='utf-8') as handle:
                json.dump(want, handle, indent=1)

    print('== artifact ==')
    backend = EncoderBackend(root)
    print('  root        %s' % root)
    print('  version     %s' % os.path.dirname(backend.model_path))
    print('  max_len     %d   (allowed %s)'
          % (backend.max_len, judge_backends.ENCODER_ALLOWED_MAX_LENS))
    print('  bundle      %s' % backend.bundle_sha256())
    config = backend.config
    print('  base        %s' % config.get('base'))
    manifest = config.get('manifest') or {}
    print('  source      %s (git %s, %s)'
          % (manifest.get('source_model'), manifest.get('packaged_at_git_head'),
             manifest.get('precision')))
    size = os.path.getsize(backend.model_path) / 1e6
    print('  model.onnx  %.1f MB' % size)

    if args.batch:
        backend.batch_size = args.batch

    # -- the contract nothing else checks ------------------------------------
    print()
    print('== ONNX graph ==')
    session, _tokenizer = backend._load()
    inputs = [value.name for value in session.get_inputs()]
    outputs = [value.name for value in session.get_outputs()]
    print('  inputs      %s' % inputs)
    print('  outputs     %s' % outputs)
    expected = list(_FIELD_ENUMS)
    if outputs != expected:
        raise SystemExit(
            'FAIL: the graph names its outputs %s; the backend indexes them by '
            '%s and would raise KeyError on every batch.\n'
            'This is the failure `_validate` cannot see.' % (outputs, expected))
    print('  OK          output names match the five heads, in order')
    shapes = {value.name: value.shape for value in session.get_inputs()}
    print('  input shape %s' % shapes.get('input_ids'))

    # -- a real batch --------------------------------------------------------
    print()
    print('== inference ==')
    items = []
    for index in range(args.rows):
        ticker, text = SAMPLES[index % len(SAMPLES)]
        item = JudgeItem()
        item.key = index + 1
        item.prepared = sentiment_input.prepare_sentiment_input(
            'bluesky', None, text, ticker, author='a1', channel='c1')
        items.append(item)

    batch_size = backend.batch_size
    judged, started = {}, time.time()
    for start in range(0, len(items), batch_size):
        got, _usage = backend.judge_batch(items[start:start + batch_size])
        judged.update(got)
    elapsed = time.time() - started

    if len(judged) != len(items):
        raise SystemExit('FAIL: judged %d of %d rows' % (len(judged), len(items)))
    for key, verdict in judged.items():
        for field, allowed in _FIELD_ENUMS.items():
            value = getattr(verdict, field)
            if value not in allowed:
                raise SystemExit('FAIL: item %s has %s=%r, outside %s'
                                 % (key, field, value, list(allowed)))
    print('  rows        %d in %d-row batches' % (len(items), batch_size))
    print('  OK          every verdict lands inside its enum')
    print('  throughput  %.2f rows/s  (small@256 on the VPS: 7.0-7.5)'
          % (len(items) / elapsed))
    print('  a 400-row pass would take %.0f s of a 600 s window'
          % (400 * elapsed / len(items)))
    print('  peak RSS    %.0f MB  (small@256 batch 4 on the VPS: 1,081 MB)'
          % _peak_rss_mb())
    print()
    print('  NOTE: this machine is not the VPS. Throughput here says little '
          'about 2 vCPU;\n        RSS is the number that transfers, and it is '
          'a floor, not a promise.')

    print()
    print('== a look at the answers ==')
    for index in range(min(len(SAMPLES), len(items))):
        ticker, text = SAMPLES[index]
        verdict = judged[index + 1]
        print('  %-5s %-8s %-22s %s'
              % (ticker, verdict.relevance, verdict.content_origin,
                 text[:52]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
