"""LOCAL-QA mutation check for the two harness corrections and the hatch CSS.

    py -3.12 ../radar-design/artifacts/ha1/local-qa/mutation_check_localqa.py   (cwd personal_apps)

Each mutant rewrites ONE file on disk, runs only the focused tests in a
subprocess, then restores the original bytes and verifies the SHA-256. A
mutant must make its tests FAIL. Written because these tests were added after
the harness edits, not before: this is the evidence that they catch a revert.
"""
import hashlib
import subprocess
import sys
from pathlib import Path

PERSONAL = Path(__file__).resolve().parents[4] / 'personal_apps'
GUARD = PERSONAL.parent / 'radar-design' / 'artifacts' / 'ha1' / 'review-2' / 'dbfree_guard.py'
PY_TESTS = ['tests/ha1_unit/test_ha1_harness.py', '-k',
            'benchmark or board_quiet_window or run2_harness or widened_statement']
CSS_TEST = ['npx.cmd', 'vitest', 'run', '-c', 'vite.radar.config.ts', 'static/radar/src/hub/analysisCss.test.ts']

MUTANTS = [
    ('cpu probe back to BENCHMARK', 'scratchpad/ha1/ha1_harness.py',
     "CPU_PROBE_SQL = 'SELECT COUNT(*) AS value FROM seq_1_to_1000000000 WHERE MOD(seq, 7) = 3'",
     "CPU_PROBE_SQL = 'SELECT BENCHMARK(50000000, SHA2(1, 512)) AS value'", 'py'),
    ('fixtures bypass CPU_PROBE_SQL once', 'scratchpad/ha1/ha1_fixtures.py',
     "rows = store._rows(harness.CPU_PROBE_SQL, effective)",
     "rows = store._rows('SELECT BENCHMARK(50000000, SHA2(1, 512)) AS value', effective)", 'py'),
    ('one unsegmented 130 s wait', 'scratchpad/ha1/verify_preview.py',
     'for segment in harness.quiet_segments(BOARD_QUIET_MS):',
     'for segment in [BOARD_QUIET_MS]:', 'py'),
    ('segments drop the remainder', 'scratchpad/ha1/ha1_harness.py',
     "return [int(segment_ms)] * whole + ([rest] if rest else [])",
     "return [int(segment_ms)] * whole", 'py'),
    ('filter-only check back to substring', 'scratchpad/ha1/verify_preview.py',
     "c.check('t' not in parse_qs(urlsplit(page.url).query),",
     "c.check('t=' not in page.evaluate('location.search'),", 'py'),
    ('skip link reuses the busy page', 'scratchpad/ha1/verify_preview.py',
     'tab_page = context.new_page()', 'tab_page = page', 'py'),
    ('timeout case back in the shared tab', 'scratchpad/ha1/verify_preview.py',
     "                with harness.case(results, 'timeout_error') as c:\n                    injected = context.new_page()",
     "                with harness.case(results, 'timeout_error') as c:\n                    injected = page", 'py'),
    ('no proof the injection engaged', 'scratchpad/ha1/verify_preview.py',
     "c.check(len(aborted) >= 1, f'no company request was aborted ({len(aborted)})')",
     "c.check(True, 'aborted')", 'py'),
    ('traced allocation keeps the 2 s limit', 'scratchpad/ha1/probe_analysis.py',
     'store = CountingStore(statement_floor_s=harness.TRACED_STATEMENT_LIMIT_S)',
     'store = CountingStore()', 'py'),
    ('author fill reaches partial bars again', 'static/radar/src/hub/analysis.css',
     '.rh-an-fill:not(.partial) { fill: var(--chatter); }',
     '.rh-an-fill { fill: var(--chatter); }', 'css'),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(kind):
    command = ([sys.executable, '-m', 'pytest', '--confcutdir=tests/ha1_unit', '-q', *PY_TESTS]
               if kind == 'py' else CSS_TEST)
    done = subprocess.run(command, cwd=PERSONAL, capture_output=True, text=True, encoding='utf-8',
                          errors='replace')
    tail = (done.stdout + done.stderr).strip().splitlines()[-3:]
    return done.returncode, ' | '.join(tail)


results = []
for kind in ('py', 'css'):
    code, tail = run(kind)
    results.append(('baseline ' + kind, code, tail))
    print(f'baseline {kind}: exit {code} :: {tail}', flush=True)
for name, relative, old, new, kind in MUTANTS:
    path = PERSONAL / relative
    original, digest = path.read_bytes(), sha(path)
    text = original.decode('utf-8')
    if text.count(old) != 1:
        print(f'MUTANT NOT APPLICABLE {name}: anchor found {text.count(old)} times', flush=True)
        results.append((name, None, 'not applicable'))
        continue
    try:
        path.write_bytes(text.replace(old, new).encode('utf-8'))
        code, tail = run(kind)
    finally:
        path.write_bytes(original)
    restored = sha(path) == digest
    caught = code not in (0, None)
    print(f'{"CAUGHT" if caught else "SURVIVED"} {name}: exit {code}; restored={restored} :: {tail}', flush=True)
    results.append((name, code, tail))
    if not restored:
        raise SystemExit(f'restore failed for {relative}')
survivors = [name for name, code, _ in results if not name.startswith('baseline') and code in (0, None)]
baseline_bad = [name for name, code, _ in results if name.startswith('baseline') and code != 0]
print(f'mutants caught {len(MUTANTS) - len(survivors)}/{len(MUTANTS)}; baseline failures {baseline_bad}')
raise SystemExit(1 if survivors or baseline_bad else 0)
