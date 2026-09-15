"""CORRECTION-2 DB-free reproductions (Implementer, 2026-09-15).

Run from candidate/personal_apps through REVIEW-2's socket guard:

    py -3.12 ../radar-design/artifacts/ha1/review-2/dbfree_guard.py \
        ../radar-design/artifacts/ha1/correction-2/repro_correction2.py

Imports neither the Radar application nor a database driver; opens no socket.
Runs one real `git` subprocess against the candidate under Git's own
foreign-owner simulation with global/system configuration isolated, and
app.py's own member gate in a toy Flask app. Writes fingerprint-inputs.txt
beside this file.
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CANDIDATE = HERE.parents[3]
PERSONAL_APPS = CANDIDATE / 'personal_apps'
sys.path.insert(0, str(PERSONAL_APPS))
sys.path.insert(0, str(PERSONAL_APPS / 'scratchpad' / 'ha1'))

import ha1_harness as harness  # noqa: E402
import local_runtime  # noqa: E402

out = {}

# U1 -- runtime Git under a foreign owner, on the actual candidate.
global_before = subprocess.run(['git', 'config', '--global', '--get-all', 'safe.directory'],
                               capture_output=True, text=True).stdout
saved = {key: os.environ.get(key) for key in ('GIT_TEST_ASSUME_DIFFERENT_OWNER', 'GIT_CONFIG_GLOBAL',
                                              'GIT_CONFIG_NOSYSTEM')}
with tempfile.TemporaryDirectory() as isolated:
    os.environ.update({'GIT_TEST_ASSUME_DIFFERENT_OWNER': '1',
                       'GIT_CONFIG_GLOBAL': str(Path(isolated) / 'global.gitconfig'),
                       'GIT_CONFIG_NOSYSTEM': '1'})
    try:
        plain = subprocess.run(['git', '-C', str(CANDIDATE), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        try:
            scoped = local_runtime.git('rev-parse', 'HEAD')
        except SystemExit as exc:
            scoped = f'SystemExit: {exc}'
        try:
            local_runtime.git('rev-parse', 'HEAD', candidate=Path(isolated) / 'missing')
            failure = 'no SystemExit'
        except SystemExit as exc:
            failure = f'SystemExit: {str(exc)[:120]}'
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
global_after = subprocess.run(['git', 'config', '--global', '--get-all', 'safe.directory'],
                              capture_output=True, text=True).stdout
out['U1_git'] = {
    'git_version': subprocess.run(['git', '--version'], capture_output=True, text=True).stdout.strip(),
    'plain_form_CORRECTION-1': {'exit': plain.returncode, 'stderr_first_line': plain.stderr.splitlines()[0]
                                if plain.stderr else ''},
    'local_runtime.git_CORRECTION-2': scoped,
    'failure_is': failure,
    'global_safe_directory_unchanged': global_before == global_after,
}

# U4 -- app.py's own member gate in a toy app (loaded from the unit-test module).
spec = importlib.util.spec_from_file_location(
    'ha1_gate_tests', PERSONAL_APPS / 'tests' / 'ha1_unit' / 'test_ha1_harness.py')
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
app = tests.toy_app()
with app.test_client() as client:
    with client.session_transaction() as flask_session:
        flask_session['user_id'] = tests.MEMBER_ID
    old = client.get(tests.COMPANY, base_url=f'http://{tests.HOST}').status_code
with app.test_client() as client:
    member = harness.host_session_get(client, tests.HOST, tests.MEMBER_ID, tests.COMPANY).status_code
    admin = harness.host_session_get(client, tests.HOST, tests.ADMIN_ID, tests.COMPANY).status_code
with app.test_client() as client:
    loopback = harness.host_session_get(client, '127.0.0.1', tests.MEMBER_ID, tests.COMPANY).status_code
with tests.toy_app(remove_member_gate=True).test_client() as client:
    removed = harness.host_session_get(client, tests.HOST, tests.MEMBER_ID, tests.COMPANY).status_code
out['U4_host_gate'] = {
    'CORRECTION-1_form_session_on_default_host': old,
    'CORRECTION-2_non_admin_session_on_full_access_host': member,
    'admin_on_full_access_host': admin,
    'non_admin_on_loopback': loopback,
    'member_gate_removed_non_admin_on_full_access_host': removed,
}

# U6 / U9 -- vacuous cases, attribution, contrast.
results = {}
with harness.case(results, 'contrast_text'):
    pass  # CORRECTION-1: every pair skipped -> zero checks -> recorded as success
with harness.cases(results, ('resolve_pin_replace', 'de_entry_us_label'), '390') as (a, b):
    a.check(True, 'reached')
    raise TimeoutError('selector never appeared')
dark = [{'node': 'div.rh', 'color': 'rgb(17, 35, 49)', 'image': False}]
out['U6_U9_cases_and_contrast'] = {
    'zero_check_case': results['contrast_text']['failures'],
    'shared_block_exception': {name: results[name]['failures']
                               for name in ('resolve_pin_replace', 'de_entry_us_label')},
    'empty_selector': harness.contrast_failures(
        [{'selector': '.rh-an-caption', 'property': 'color', 'matched': 0, 'pairs': []}],
        minimum=4.5, kind='text')[0],
    'unsupported_colour': harness.contrast_failures(
        [{'selector': 'main h1', 'property': 'color', 'matched': 1,
          'pairs': [{'value': 'oklch(80% 0.1 200)', 'layers': dark}]}], minimum=4.5, kind='text')[0],
    'translucent_text_on_panel': harness.contrast_failures(
        [{'selector': '.rh-an-dayfacts', 'property': 'color', 'matched': 1,
          'pairs': [{'value': 'rgba(255, 255, 255, 0.2)', 'layers': dark}]}], minimum=4.5, kind='text')[0],
    'no_opaque_background': harness.contrast_failures(
        [{'selector': 'svg .rh-an-axis', 'property': 'fill', 'matched': 1,
          'pairs': [{'value': 'rgb(255, 255, 255)', 'layers': [{'node': 'svg', 'color': 'rgba(0, 0, 0, 0)',
                                                                'image': False}]}]}],
        minimum=4.5, kind='text')[0],
}

# U5 -- the sub-second limit as the production budget renders it (no engine).
from features.radar import analysis  # noqa: E402  (extensions only; no app, no engine)


class _Dialect:
    name, is_mariadb = 'mysql', True


class _Session:
    def get_bind(self):
        return type('Bind', (), {'dialect': _Dialect()})()


budget = analysis.ReaderBudget(seconds=harness.SUBSECOND_REQUEST_S)
effective = budget.statement_timeout()
out['U5_subsecond_rendering'] = {'requested_s': harness.SUBSECOND_REQUEST_S, 'effective_s': effective,
                                 'rendered': analysis.SqlStore(_Session())._timed('SELECT 1', effective)}

# U8 -- the covered inputs of the candidate right now.
fingerprint = harness.source_fingerprint(CANDIDATE)
(HERE / 'fingerprint-inputs.txt').write_text(
    f'# ha1_harness.source_fingerprint({CANDIDATE.as_posix()})\n'
    f'# digest {fingerprint["digest"]} (moves with every later edit; identity, not a pin)\n'
    f'# include {list(harness.FINGERPRINT_INCLUDE)}\n# exclude {list(harness.FINGERPRINT_EXCLUDE)}\n'
    + '\n'.join(f'{sha}  {name}' for name, sha in fingerprint['files'].items()) + '\n', encoding='utf-8')
groups = {}
for name in fingerprint['files']:
    key = ('build' if name.startswith(harness.BUILD_PREFIX) else
           'frontend-src' if '/static/radar/src/' in name else
           'ha1-harness' if '/scratchpad/ha1/' in name else
           'templates' if '/templates/' in name else 'python-app')
    groups[key] = groups.get(key, 0) + 1
out['U8_fingerprint'] = {'digest': fingerprint['digest'], 'files': len(fingerprint['files']),
                         'build_files': fingerprint['build_files'], 'by_group': groups}

# U10 -- an engine that has not connected is not labelled.
import sqlalchemy as sa  # noqa: E402

engine = sa.create_engine('sqlite://')
out['U10_dialect_before_connect'] = harness.dialect_record(engine.dialect, lambda: 'never read')

print(json.dumps(out, indent=2, default=str))
