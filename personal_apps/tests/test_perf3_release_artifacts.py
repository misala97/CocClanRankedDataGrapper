"""Executable, local proof for PERF3's unexecuted release artifacts.

Every test here drives the REAL `deploy_perf3.sh` under bash, against fake
`systemctl`/`git`/`npm`/`pip`/`flask`/`python` commands. The fakes can be made
to FAIL on demand, because the first version of this file could not fail any of
them and four defects walked straight through it: a checkout reset that failed
partway was treated as untouched, a service that failed to start on the SUCCESS
path re-entered the rollback trap and undid a healthy release, the rollback path
ran `flask db upgrade` against code that cannot resolve the new stamp, and the
`.env` rewrite never checked `awk` before replacing the file.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'radar-design/perf3-release/deploy_perf3.sh'
ROLLBACK = ROOT / 'radar-design/perf3-release/rollback-compatible.json'
NEW_SHA = 'b' * 40
OLD_SHA = '197be30c2c1028c0b46f8110783f1da5e428d481'
MIGRATION = 'b7e3f9c1a2d4'
NON_WEB = ('coc_scheduler', 'personal_apps_gym_notifier', 'radar_ingest')
WEB = ('personal_apps_web', 'coc_web')


def _exe(path, text):
    path.write_text('#!/usr/bin/env bash\nset -eu\n' + text,
                    encoding='utf-8')
    path.chmod(0o755)
    return str(path).replace('\\', '/')


@pytest.fixture()
def release_env(tmp_path):
    bash = shutil.which('bash')
    if not bash:
        candidate = Path('C:/Program Files/Git/bin/bash.exe')
        bash = str(candidate) if candidate.exists() else None
    if not bash:
        pytest.fail('bash is required to verify the proposed release runner')
    log = tmp_path / 'commands.log'
    head = tmp_path / 'head'
    head.write_text(OLD_SHA, encoding='ascii')
    count = tmp_path / 'readiness-count'
    count.write_text('0', encoding='ascii')
    upgrades = tmp_path / 'upgrade-count'
    upgrades.write_text('0', encoding='ascii')
    state = tmp_path / 'unit-state'
    state.mkdir()
    repo = tmp_path / 'repo'
    (repo / 'personal_apps').mkdir(parents=True)
    (repo / 'coc_stats').mkdir()
    env_file = repo / '.env'
    unit_source = tmp_path / 'radar_board_producer.service'
    unit_source.write_text('[Service]\nExecStart=/bin/true\n', encoding='utf-8')
    unit_target = tmp_path / 'installed.service'
    command = tmp_path / 'fake-command.sh'
    fake = _exe(command, r'''
role="$1"; shift
printf '%s %s\n' "$role" "$*" >> "$FAKE_COMMAND_LOG"
# Reject real missing-unit mutations; it exists only after the runner installs it.
if [ "$role" = systemctl ] && [ "${2:-}" = radar_board_producer.service ] && [ "${FAKE_ABSENT_PRODUCER:-0}" = 1 ] && [ ! -f "$PERF3_UNIT_TARGET" ]; then
  case "$1" in
    show) echo not-found; exit 0;;
    is-active|is-enabled) exit 4;;
    start|stop|disable|enable) echo 'Unit not found' >&2; exit 5;;
  esac
fi
case "$role:$1" in
  systemctl:show) echo loaded ;;
  systemctl:cat) printf 'Environment="SECRET=sentinel_quoted" "OTHER=sentinel_multi"\nEnvironment=SECRET=sentinel_bare\nEnvironment="SECRET=sentinel_cont\\\nnext"\n' ;;

  systemctl:is-active)
    # Real systemctl reports what the unit is doing NOW, so this fake tracks
    # its own starts and stops and only falls back to the captured baseline for
    # a unit this run has not touched.
    name=${2%.service}
    if [ "${FAKE_FAIL:-}" = final-health ] && [ "$name" = personal_apps_web ] && [ -e "$FAKE_STATE_DIR/$name" ] && [ "$(cat "$FAKE_STATE_DIR/$name")" = active ]; then exit 9; fi
    if [ -e "$FAKE_STATE_DIR/$name" ]; then
      [ "$(cat "$FAKE_STATE_DIR/$name")" = active ] || exit 3
      exit 0
    fi
    case " $FAKE_ACTIVE " in *" $name "*) exit 0;; *) exit 3;; esac ;;
  systemctl:is-enabled)
    name=${2%.service}; case " $FAKE_ENABLED " in *" $name "*) exit 0;; *) exit 1;; esac ;;
  systemctl:start)
    name=${2%.service}
    [ "${FAKE_FAIL_UNIT:-}" != "$name" ] || exit 5
    printf 'active' > "$FAKE_STATE_DIR/$name" ;;
  systemctl:stop)
    name=${2%.service}
    printf 'inactive' > "$FAKE_STATE_DIR/$name" ;;
  git:*)
    if [ "$1" = "-C" ]; then shift 2; fi
    case "$1" in
      rev-parse) cat "$FAKE_HEAD" ;;
      status|fetch) : ;;
      reset)
        if [ "${FAKE_FAIL:-}" = git-reset ] && [ ! -e "$FAKE_FAIL_MARK" ]; then
          : > "$FAKE_FAIL_MARK"; exit 28
        fi
        printf '%s' "$3" > "$FAKE_HEAD" ;;
    esac ;;
  npm:*)
    if [ "${FAKE_FAIL:-}" = signal-build ] && [ ! -e "$FAKE_FAIL_MARK" ]; then : > "$FAKE_FAIL_MARK"; kill -TERM "$PPID"; sleep 1; exit 143; fi
    if [ "${FAKE_FAIL:-}" = npm ] && [ ! -e "$FAKE_FAIL_MARK" ]; then
      : > "$FAKE_FAIL_MARK"; exit 23
    fi ;;
  pip:*) [ "${FAKE_FAIL:-}" != pip ] || exit 24 ;;
  flask:*)
    if [ "$1" = "db" ] && [ "${2:-}" = "upgrade" ]; then
      if [ "${FAKE_FAIL:-}" = partial-migration ]; then exit 26; fi
      if [ "${FAKE_FAIL:-}" = signal-migration ]; then kill -TERM "$PPID"; sleep 1; exit 143; fi
      n=$(cat "$FAKE_UPGRADE_COUNT"); n=$((n + 1)); printf '%s' "$n" > "$FAKE_UPGRADE_COUNT"
    fi
    [ "${FAKE_FAIL:-}" != flask ] || exit 25 ;;
  python:*)
    if [ "${FAKE_READINESS:-}" = signal ]; then kill -TERM "$PPID"; sleep 1; exit 143; fi
    if [ "${FAKE_READINESS:-}" = hang ]; then sleep 30; fi
    n=$(cat "$FAKE_READY_COUNT"); n=$((n + 1)); printf '%s' "$n" > "$FAKE_READY_COUNT"
    [ "${FAKE_READINESS:-pass}" = pass ] ;;
esac
''')
    common = {
        'PERF3_REPO': str(repo).replace('\\', '/'),
        'PERF3_ENV_FILE': str(env_file).replace('\\', '/'),
        'PERF3_UNIT_SOURCE': str(unit_source).replace('\\', '/'),
        'PERF3_UNIT_TARGET': str(unit_target).replace('\\', '/'),
        'PERF3_LOG_DIR': str(tmp_path / 'logs').replace('\\', '/'),
        'PERF3_SYSTEMCTL': fake + ' systemctl',
        'PERF3_GIT': fake + ' git',
        'PERF3_NPM': fake + ' npm',
        'PERF3_PIP': fake + ' pip',
        'PERF3_FLASK': fake + ' flask',
        'PERF3_PYTHON': fake + ' python',
        'PERF3_READINESS_ATTEMPTS': '2',
        'PERF3_READINESS_INTERVAL': '0',
        'FAKE_COMMAND_LOG': str(log).replace('\\', '/'),
        'FAKE_HEAD': str(head).replace('\\', '/'),
        'FAKE_READY_COUNT': str(count).replace('\\', '/'),
        'FAKE_UPGRADE_COUNT': str(upgrades).replace('\\', '/'),
        'FAKE_STATE_DIR': str(state).replace('\\', '/'),
        'FAKE_FAIL_MARK': str(tmp_path / 'failed-once').replace('\\', '/'),
        'FAKE_ACTIVE': ('personal_apps_web coc_web coc_scheduler '
                        'personal_apps_gym_notifier radar_ingest'),
        'FAKE_ENABLED': ('personal_apps_web coc_web coc_scheduler '
                         'personal_apps_gym_notifier radar_ingest'),
    }
    return bash, common, env_file, log, head, count, tmp_path, upgrades, unit_target


def _run(release_env, mode, **extra):
    bash, common, *_ = release_env
    env = dict(os.environ)
    env.update(common)
    env.update(extra)
    return subprocess.run([bash, str(SCRIPT), mode, NEW_SHA], env=env,
                          text=True, capture_output=True, timeout=60)


def _producer_on(**over):
    everything = ('personal_apps_web coc_web coc_scheduler '
                  'personal_apps_gym_notifier radar_ingest '
                  'radar_board_producer')
    out = {'FAKE_ACTIVE': everything, 'FAKE_ENABLED': everything}
    out.update(over)
    return out


def test_routine_rollout_stops_both_webs_until_readiness_then_restores(
        release_env):
    _, _, env_file, log, head, _, tmp, _, _ = release_env
    env_file.write_text('UNRELATED=secret\nRADAR_BOARD_SHARED_RESULTS=on\n',
                        encoding='utf-8')
    result = _run(release_env, 'routine', **_producer_on())

    assert result.returncode == 0, result.stdout + result.stderr
    commands = log.read_text(encoding='utf-8').splitlines()
    reset = next(i for i, line in enumerate(commands)
                 if line.startswith('git -C ') and line.endswith(
                     f'reset --hard {NEW_SHA}'))
    ready = next(i for i, line in enumerate(commands)
                 if line.startswith('python run_radar_board_producer.py --readiness'))
    for service in WEB:
        assert commands.index(f'systemctl stop {service}.service') < reset
        assert commands.index(f'systemctl start {service}.service') > ready
    assert head.read_text(encoding='ascii') == NEW_SHA
    text = env_file.read_text(encoding='utf-8')
    assert 'RADAR_BOARD_SHARED_RESULTS=on' in text
    assert 'UNRELATED=secret' in text, 'the rewrite dropped an unrelated key'
    durable = list((tmp / 'logs').glob('perf3-release-*.log'))
    assert len(durable) == 1 and 'release succeeded' in durable[0].read_text()


def test_a_build_failure_before_the_migration_rolls_the_checkout_back(
        release_env):
    _, _, env_file, log, head, _, _, upgrades, _ = release_env
    env_file.write_text('UNRELATED=secret\n', encoding='utf-8')
    result = _run(release_env, 'first', FAKE_FAIL='npm')

    assert result.returncode == 23, result.stdout + result.stderr
    commands = log.read_text(encoding='utf-8').splitlines()
    assert head.read_text(encoding='ascii') == OLD_SHA
    assert upgrades.read_text(encoding='ascii') == '0', (
        'the migration must not have run before a build failure')
    for service in NON_WEB + WEB:
        assert f'systemctl start {service}.service' in commands
    text = env_file.read_text(encoding='utf-8')
    assert 'RADAR_BOARD_SHARED_RESULTS' not in text
    assert 'UNRELATED=secret' in text


def test_a_reset_that_fails_partway_is_still_treated_as_a_changed_checkout(
        release_env):
    """`git reset` can fail with the tree already partly rewritten.

    The first version set CHANGED=1 only AFTER the reset returned, so a partial
    reset looked untouched: nothing was restored and both web units were started
    on a half-installed tree.
    """
    _, _, env_file, log, head, _, _, _, _ = release_env
    env_file.write_text('UNRELATED=secret\n', encoding='utf-8')
    result = _run(release_env, 'first', FAKE_FAIL='git-reset')

    assert result.returncode == 28, result.stdout + result.stderr
    commands = log.read_text(encoding='utf-8').splitlines()
    assert any(line.endswith(f'reset --hard {OLD_SHA}') for line in commands), (
        'a failed reset left the tree unrestored')
    assert head.read_text(encoding='ascii') == OLD_SHA


def test_a_readiness_timeout_keeps_the_migrated_checkout_and_recovers_flag_off(
        release_env):
    """After the migration there is no code rollback: old code cannot resolve
    the new stamp. Recovery is flag-off with the schema retained."""
    _, _, env_file, log, head, count, _, upgrades, _ = release_env
    env_file.write_text('UNRELATED=secret\n', encoding='utf-8')
    result = _run(release_env, 'first', FAKE_READINESS='fail')

    assert result.returncode == 70, result.stdout + result.stderr
    commands = log.read_text(encoding='utf-8').splitlines()
    assert count.read_text(encoding='ascii') == '2', 'readiness was not bounded'
    assert head.read_text(encoding='ascii') == NEW_SHA, (
        'the checkout was rolled back after the migration had been applied')
    assert not any(line.endswith(f'reset --hard {OLD_SHA}')
                   for line in commands)
    assert upgrades.read_text(encoding='ascii') == '2', (
        'the recovery path re-ran flask db upgrade against older code')
    for service in NON_WEB + WEB:
        assert f'systemctl start {service}.service' in commands, (
            f'{service} was left stopped by a recoverable readiness timeout')
    text = env_file.read_text(encoding='utf-8')
    assert 'RADAR_BOARD_SHARED_RESULTS=off' in text
    assert 'UNRELATED=secret' in text


def test_a_service_failure_after_activation_reports_but_never_rolls_back(
        release_env):
    """Once readiness passed and the flag is on, the release stands.

    The first version ran `restore_services` as a bare top-level command, so one
    failing `systemctl start` re-entered the ERR trap and destructively undid a
    release that had already succeeded."""
    _, _, env_file, log, head, _, _, upgrades, _ = release_env
    env_file.write_text('UNRELATED=secret\nRADAR_BOARD_SHARED_RESULTS=on\n',
                        encoding='utf-8')
    result = _run(release_env, 'routine',
                  **_producer_on(FAKE_FAIL_UNIT='coc_scheduler'))

    assert result.returncode == 75, result.stdout + result.stderr
    commands = log.read_text(encoding='utf-8').splitlines()
    assert head.read_text(encoding='ascii') == NEW_SHA
    assert not any(line.endswith(f'reset --hard {OLD_SHA}')
                   for line in commands)
    assert upgrades.read_text(encoding='ascii') == '2'
    assert 'RADAR_BOARD_SHARED_RESULTS=on' in env_file.read_text(
        encoding='utf-8'), 'a healthy release had its flag turned back off'
    # Every other unit was still attempted rather than abandoned at the first
    # failure.
    for service in WEB:
        assert f'systemctl start {service}.service' in commands


def test_a_routine_rollout_never_stops_the_producer_it_just_made_ready(
        release_env):
    """The producer's captured state can be `inactive` -- that is exactly what
    an operator leaves behind during an incident. Restoring it literally would
    turn the flag on with nothing building."""
    _, _, env_file, log, _, _, _, _, _ = release_env
    env_file.write_text('UNRELATED=secret\nRADAR_BOARD_SHARED_RESULTS=on\n',
                        encoding='utf-8')
    others = ('personal_apps_web coc_web coc_scheduler '
              'personal_apps_gym_notifier radar_ingest')
    result = _run(release_env, 'routine', FAKE_ACTIVE=others,
                  FAKE_ENABLED=others)

    assert result.returncode == 0, result.stdout + result.stderr
    commands = log.read_text(encoding='utf-8').splitlines()
    ready = next(i for i, line in enumerate(commands)
                 if line.startswith('python run_radar_board_producer.py'))
    after = commands[ready:]
    assert 'systemctl stop radar_board_producer.service' not in after
    assert 'systemctl start radar_board_producer.service' in commands[:ready]


def test_the_env_rewrite_refuses_rather_than_truncating_the_secrets_file(
        release_env):
    """`awk` writing the replacement is not assumed to have succeeded."""
    _, _, env_file, _, _, _, _, _, _ = release_env
    keys = [f'KEY_{i}=value-{i}' for i in range(40)]
    env_file.write_text('\n'.join(keys) + '\nRADAR_BOARD_SHARED_RESULTS=on\n',
                        encoding='utf-8')
    result = _run(release_env, 'routine', **_producer_on())

    assert result.returncode == 0, result.stdout + result.stderr
    text = env_file.read_text(encoding='utf-8')
    for key in keys:
        assert key in text, f'{key} did not survive the .env rewrite'
    assert text.count('RADAR_BOARD_SHARED_RESULTS=') == 1


def test_the_first_rollout_refuses_a_flag_that_is_already_on_in_any_spelling(
        release_env):
    _, _, env_file, _, head, _, _, _, _ = release_env
    env_file.write_text('UNRELATED=secret\nRADAR_BOARD_SHARED_RESULTS="ON"\n',
                        encoding='utf-8')
    result = _run(release_env, 'first')

    assert result.returncode != 0
    assert head.read_text(encoding='ascii') == OLD_SHA


def test_the_rollback_manifest_names_real_older_code_that_retains_the_revision():
    artifact = json.loads(ROLLBACK.read_text(encoding='utf-8'))
    commit = artifact['commit']
    migration = artifact['retained_migration']
    assert artifact['retained_migration'].endswith('.py')
    # The file existing at that tree is not enough: a rename or an edited
    # `revision = ` would pass that. Read the blob and check the identity.
    blob = subprocess.run(
        ['git', '-c', f'safe.directory={ROOT}', '-C', str(ROOT),
         'show', f'{commit}:{migration}'], capture_output=True, text=True)
    assert blob.returncode == 0, blob.stderr
    assert f"revision = '{MIGRATION}'" in blob.stdout, (
        f'{commit} does not define migration {MIGRATION}')
    # And it must really be an ancestor of what would ship.
    ancestor = subprocess.run(
        ['git', '-c', f'safe.directory={ROOT}', '-C', str(ROOT),
         'merge-base', '--is-ancestor', commit, 'HEAD'], capture_output=True)
    assert ancestor.returncode == 0, (
        f'{commit} is not an ancestor of HEAD, so it is not a rollback target')


@pytest.mark.parametrize('failure', ['', 'npm'])
def test_first_rollout_handles_genuinely_absent_producer(release_env, failure):
    _, _, env_file, log, _, _, _, _, _ = release_env
    env_file.write_text('UNRELATED=secret\n')
    result = _run(release_env, 'first', FAKE_ABSENT_PRODUCER='1', FAKE_FAIL=failure)
    assert result.returncode == (23 if failure else 0), result.stdout + result.stderr
    commands = log.read_text().splitlines()
    for unit in WEB:
        assert f'systemctl start {unit}.service' in commands
    assert 'Unit not found' not in result.stdout + result.stderr


@pytest.mark.parametrize('failure', ['partial-migration', 'signal-migration'])
def test_incomplete_migration_never_restarts_consumers(release_env, failure):
    _, _, env_file, log, head, _, _, _, _ = release_env
    env_file.write_text('UNRELATED=secret\n')
    result = _run(release_env, 'first', FAKE_FAIL=failure)
    assert result.returncode != 0, result.stdout
    assert head.read_text() == NEW_SHA
    assert 'manual recovery' in result.stdout
    assert not any(line.startswith('systemctl start ') for line in log.read_text().splitlines())


def test_routine_readiness_failure_forces_off_and_stops_producer(release_env):
    _, _, env_file, log, _, _, _, _, _ = release_env
    env_file.write_text('UNRELATED=secret\nRADAR_BOARD_SHARED_RESULTS=on\n')
    result = _run(release_env, 'routine', **_producer_on(FAKE_READINESS='fail'))
    assert result.returncode == 70, result.stdout
    assert 'RADAR_BOARD_SHARED_RESULTS=off' in env_file.read_text()
    lines = log.read_text().splitlines()
    assert lines.index('systemctl start radar_board_producer.service') < max(i for i,x in enumerate(lines) if x == 'systemctl stop radar_board_producer.service')


def test_postactivation_health_failure_retains_activation(release_env):
    _, _, env_file, _, head, _, _, _, _ = release_env
    env_file.write_text('UNRELATED=secret\n')
    result = _run(release_env, 'first', FAKE_FAIL='final-health')
    assert result.returncode == 75, result.stdout
    assert 'activation degraded' in result.stdout
    assert head.read_text() == NEW_SHA
    assert 'RADAR_BOARD_SHARED_RESULTS=on' in env_file.read_text()


def test_unit_environment_secrets_never_enter_any_log(release_env):
    _, _, env_file, log, _, _, tmp, _, _ = release_env
    env_file.write_text('UNRELATED=secret\n')
    result = _run(release_env, 'first')
    assert result.returncode == 0, result.stdout
    contents = result.stdout + result.stderr + ''.join(p.read_text() for p in (tmp/'logs').glob('*'))
    assert 'sentinel_' not in contents
    assert 'systemctl cat ' not in log.read_text()
    shows = [line for line in log.read_text().splitlines() if line.startswith('systemctl show')]
    assert shows and all('--property=LoadState' in line for line in shows)


def test_hanging_readiness_probe_respects_real_deadline(release_env):
    _, _, env_file, _, _, _, _, _, _ = release_env
    env_file.write_text('UNRELATED=secret\n')
    started = time.monotonic()
    result = _run(release_env, 'first', FAKE_READINESS='hang', PERF3_READINESS_SECONDS='2', PERF3_PROBE_SECONDS='1', PERF3_READINESS_ATTEMPTS='180')
    assert result.returncode == 70, result.stdout + result.stderr
    # Includes shell startup and recovery on Windows; a hung 30-second probe must not survive.
    assert time.monotonic() - started < 15


def test_interrupted_build_restores_original_checkout(release_env):
    _, _, env_file, log, head, _, _, _, _ = release_env
    env_file.write_text('UNRELATED=secret\n')
    result = _run(release_env, 'first', FAKE_FAIL='signal-build')
    assert result.returncode != 0
    assert head.read_text() == OLD_SHA
    for unit in WEB:
        assert f'systemctl start {unit}.service' in log.read_text()
