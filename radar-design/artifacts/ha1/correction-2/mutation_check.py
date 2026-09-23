"""CORRECTION-2 mutation check: do the new DB-free regressions have teeth?

Run from candidate/personal_apps:

    py -3.12 ../radar-design/artifacts/ha1/correction-2/mutation_check.py

For each mutation, a fresh subprocess blocks sockets (as REVIEW-2's guard),
loads ha1_harness.py or local_runtime.py with ONE exact-string change applied
IN MEMORY (no file is edited), registers it in sys.modules, and runs the
matching tests. A mutant must be caught: pytest exit 1 with failed tests. A
baseline run with no change must pass, so a failure cannot be a bootstrap
error. Prints a table and exits 1 if any mutant survives.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HA1 = Path.cwd() / 'scratchpad' / 'ha1'
TESTS = 'tests/ha1_unit/test_ha1_harness.py'
SELECTION = ('TestRuntimeGit or TestCaseRecording or TestContrast or TestFullAccessHostGate or '
             'TestFingerprint or TestTimeout or TestCleanupReport or TestDeadline or TestDialect')

MUTATIONS = [
    ('baseline (no change)', 'ha1_harness', None, None, SELECTION),
    ('U1 runtime Git without per-command safe.directory', 'local_runtime',
     "command = ['git', '-c', f'safe.directory={root.as_posix()}', '-C', str(root), *args]",
     "command = ['git', '-C', str(root), *args]", 'TestRuntimeGit'),
    ('U1 Git failure not a SystemExit', 'local_runtime',
     "    if completed.returncode != 0:\n", "    if False:\n", 'TestRuntimeGit'),
    ('U4 session set on the default host', 'ha1_harness',
     'with client.session_transaction(base_url=base_url) as flask_session:',
     'with client.session_transaction() as flask_session:', 'TestFullAccessHostGate'),
    ('U6 zero-check case recorded as success', 'ha1_harness',
     'elif case.checks == 0 and not case.unsupported_checks:', 'elif False:', 'TestCaseRecording'),
    ('U9 shared-block exception attributed to the last case only', 'ha1_harness',
     '            record_case(results, one, raised)',
     '            record_case(results, one, raised if one is current[-1] else None)', 'TestCaseRecording'),
    ('U9 unsupported check recorded as success', 'ha1_harness',
     "    problems += [f'UNSUPPORTED, not a pass: {message}' for message in case.unsupported_checks]\n",
     '', 'TestCaseRecording'),
    ('U6 unsupported colour skipped (CORRECTION-1 behaviour)', 'ha1_harness',
     "                failures.append(f'{where}: {exc}; unverified, not skipped')\n", '', 'TestContrast'),
    ('U6 empty required selector skipped', 'ha1_harness',
     "            failures.append(f'{where}: required selector matched no rendered element')\n", '',
     'TestContrast'),
    ('U6 alpha ignored', 'ha1_harness',
     'ratio = contrast_ratio(composite(foreground, alpha, background), background)',
     'ratio = contrast_ratio(foreground, background)', 'TestContrast'),
    ('U8 harness outputs under radar-design/artifacts not excluded', 'ha1_harness',
     "    'radar-design/artifacts/*', '*.test.ts', '*.test.tsx',", "    '*.test.ts', '*.test.tsx',",
     'TestFingerprint'),
    ('U8 frontend test files fingerprinted', 'ha1_harness',
     "    'radar-design/artifacts/*', '*.test.ts', '*.test.tsx',", "    'radar-design/artifacts/*',",
     'TestFingerprint'),
    ('U8 drift not reported', 'ha1_harness',
     "    elif started.get('digest') != current.get('digest'):", '    elif False:', 'TestFingerprint'),
    ('U5 sub-second probe not required', 'ha1_harness',
     "    failures += subsecond_failures(probes.get('cpu_subsecond'))\n", '', 'TestTimeout'),
    ('U5 recovery not required', 'ha1_harness',
     "    if result.get('recovery_ok') is not True:", '    if False:', 'TestTimeout'),
    ('U7 cleanup failure dropped from the report', 'ha1_harness',
     "    if cleanup['status'] == 'incomplete':\n        failures.append", "    if False:\n        failures.append",
     'TestCleanupReport'),
    ('Deadline: an exhausted budget answering 200 accepted', 'ha1_harness',
     "        if part.get('status') == 200 or part.get('code') != 'analysis_limit':", '        if False:',
     'TestDeadline'),
    ('U10 dialect labelled before any connection', 'ha1_harness',
     '    if version is None:\n', '    if False:\n', 'TestDialect'),
]

BOOTSTRAP = r'''
import json, os, socket, sys, types
sys.path.insert(0, os.getcwd())
ha1 = os.path.join(os.getcwd(), 'scratchpad', 'ha1')
sys.path.insert(0, ha1)
def _refuse(*a, **k):
    raise RuntimeError('mutation guard: socket connect attempted')
socket.socket.connect = _refuse
socket.socket.connect_ex = _refuse
socket.create_connection = _refuse
name, old, new, selection, tests = json.loads(sys.argv[1])
path = os.path.join(ha1, name + '.py')
source = open(path, encoding='utf-8').read()
if old is not None:
    assert source.count(old) == 1, ('mutation anchor not unique or missing', name, old)
    source = source.replace(old, new)
module = types.ModuleType(name)
module.__file__ = path
sys.modules[name] = module
exec(compile(source, path, 'exec'), module.__dict__)
import pytest
code = pytest.main(['-p', 'no:cacheprovider', '--confcutdir=tests/ha1_unit', tests, '-q', '-k', selection])
print('guard: app_imported=%s pymysql_imported=%s' % ('app' in sys.modules, 'pymysql' in sys.modules))
sys.exit(code)
'''


def main():
    rows, survived = [], []
    for label, module, old, new, selection in MUTATIONS:
        completed = subprocess.run([sys.executable, '-c', BOOTSTRAP,
                                    json.dumps([module, old, new, selection, TESTS])],
                                   capture_output=True, text=True)
        text = completed.stdout + completed.stderr
        summary = next((line for line in reversed(text.splitlines()) if re.search(r'\d+ (passed|failed)', line)), '')
        guard = next((line for line in text.splitlines() if line.startswith('guard:')), '')
        if old is None:
            ok = completed.returncode == 0 and 'failed' not in summary
        else:
            ok = completed.returncode == 1 and 'failed' in summary
        rows.append((label, completed.returncode, summary.strip(), guard, 'OK' if ok else 'SURVIVED/ERROR'))
        if not ok:
            survived.append(label)
            print(text[-2000:], file=sys.stderr)
    for row in rows:
        print(' | '.join(str(part) for part in row))
    print(f'mutants caught: {sum(1 for r in rows[1:] if r[4] == "OK")}/{len(rows) - 1}; '
          f'baseline {"passed" if rows[0][4] == "OK" else "FAILED"}')
    raise SystemExit(1 if survived else 0)


if __name__ == '__main__':
    main()
