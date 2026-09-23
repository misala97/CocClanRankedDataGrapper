"""TEST-ONLY child programs for test_child_lifecycle.py.

Each is started by the PRODUCTION subprocess launcher as a fresh interpreter,
`python -E -s -B -m tests.selected_price_unit.child_targets <behaviour>`, with
the production minimal environment and pipes, so the supervisor, reader,
deadline and reaping under test are the real ones. They may only use what the
production child may use. Nothing in production imports or selects this
module.
"""
import json
import os
import sys
import time

from features.radar import price_chart_fetch as fetch

HEAVY = ('flask', 'flask_sqlalchemy', 'sqlalchemy', 'extensions', 'models', 'app', 'auth', 'dotenv')


def _series(spec):
    return {'kind': 'ok', 'bars': [[spec['anchor'], 101.5]], 'off_grid': 0, 'outside': 0,
            'nulls': 0, 'received_at': time.time(), 'child_pid': os.getpid(),
            'loaded': sorted(name for name in HEAVY if name in sys.modules),
            'env_keys': sorted(os.environ)}


def _write(data):
    out = sys.stdout.buffer
    out.write(data)
    out.flush()


def main():
    behaviour = sys.argv[1]
    if behaviour == 'early_exit':            # dies before reading its request
        os._exit(3)
    spec = json.loads(sys.stdin.buffer.read(fetch.SPEC_LIMIT_BYTES + 1))
    if behaviour == 'normal':
        _write(fetch.encode_result(_series(spec)))
    elif behaviour == 'hanging':             # never answers, never exits
        time.sleep(120)
    elif behaviour == 'oversized':           # 4 MiB: blocks once the pipe is full
        chunk = b'x' * fetch.CHUNK_BYTES
        for _ in range(64):
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        time.sleep(120)
    elif behaviour == 'stderr_flood':        # 8 MiB of diagnostics, then a normal answer
        for _ in range(128):
            sys.stderr.buffer.write(b'e' * fetch.CHUNK_BYTES)
        sys.stderr.buffer.flush()
        _write(fetch.encode_result(_series(spec)))
    elif behaviour == 'garbage':
        _write(b'not json at all')
    elif behaviour == 'nonzero':             # a complete answer, then a failed exit
        _write(fetch.encode_result(_series(spec)))
        sys.exit(5)
    else:
        sys.exit(9)
    return 0


if __name__ == '__main__':
    sys.exit(main())
