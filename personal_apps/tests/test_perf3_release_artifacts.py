"""Executable, local proof for PERF3's unexecuted release artifacts."""
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'radar-design/perf3-release/deploy_perf3.sh'
ROLLBACK = ROOT / 'radar-design/perf3-release/rollback-compatible.json'
NEW_SHA = 'b' * 40
OLD_SHA = '197be30c2c1028c0b46f8110783f1da5e428d481'


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
    repo = tmp_path / 'repo'
    (repo / 'personal_apps').mkdir(parents=True)
    env_file = repo / '.env'
    unit_source = tmp_path / 'radar_board_producer.service'
    unit_source.write_text('[Service]\nExecStart=/bin/true\n', encoding='utf-8')
    unit_target = tmp_path / 'installed.service'
    command = tmp_path / 'fake-command.sh'
    fake = _exe(command, r'''
role="$1"; shift
printf '%s %s\n' "$role" "$*" >> "$FAKE_COMMAND_LOG"
case "$role:$1" in
  systemctl:is-active)
    name=${2%.service}; case " $FAKE_ACTIVE " in *" $name "*) exit 0;; *) exit 3;; esac ;;
  systemctl:is-enabled)
    name=${2%.service}; case " $FAKE_ENABLED " in *" $name "*) exit 0;; *) exit 1;; esac ;;
  git:*)
    if [ "$1" = "-C" ]; then shift 2; fi
    case "$1" in
      rev-parse) cat "$FAKE_HEAD" ;;
      status|fetch) : ;;
      reset) printf '%s' "$3" > "$FAKE_HEAD" ;;
    esac ;;
  npm:*)
    if [ "${FAKE_FAIL:-}" = npm ] && [ ! -e "$FAKE_FAIL_MARK" ]; then
      : > "$FAKE_FAIL_MARK"; exit 23
    fi ;;
  pip:*) [ "${FAKE_FAIL:-}" != pip ] || exit 24 ;;
  flask:*) [ "${FAKE_FAIL:-}" != flask ] || exit 25 ;;
  python:*)
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
        'FAKE_FAIL_MARK': str(tmp_path / 'failed-once').replace('\\', '/'),
        'FAKE_ACTIVE': ('personal_apps_web coc_web coc_scheduler '
                        'personal_apps_gym_notifier radar_ingest'),
        'FAKE_ENABLED': ('personal_apps_web coc_web coc_scheduler '
                         'personal_apps_gym_notifier radar_ingest'),
    }
    return bash, common, env_file, log, head, count, tmp_path


def _run(release_env, mode, **extra):
    bash, common, *_ = release_env
    env = dict(os.environ)
    env.update(common)
    env.update(extra)
    return subprocess.run([bash, str(SCRIPT), mode, NEW_SHA], env=env,
                          text=True, capture_output=True, timeout=30)


def test_routine_rollout_stops_both_webs_until_readiness_then_restores(
        release_env):
    _, _, env_file, log, head, _, tmp = release_env
    env_file.write_text('UNRELATED=secret\nRADAR_BOARD_SHARED_RESULTS=on\n',
                        encoding='utf-8')
    result = _run(
        release_env, 'routine',
        FAKE_ACTIVE=('personal_apps_web coc_web coc_scheduler '
                     'personal_apps_gym_notifier radar_ingest '
                     'radar_board_producer'),
        FAKE_ENABLED=('personal_apps_web coc_web coc_scheduler '
                      'personal_apps_gym_notifier radar_ingest '
                      'radar_board_producer'))

    assert result.returncode == 0, result.stdout + result.stderr
    commands = log.read_text(encoding='utf-8').splitlines()
    reset = next(i for i, line in enumerate(commands)
                 if line.startswith('git -C ') and line.endswith(
                     f'reset --hard {NEW_SHA}'))
    ready = next(i for i, line in enumerate(commands)
                 if line.startswith('python run_radar_board_producer.py --readiness'))
    assert commands.index('systemctl stop personal_apps_web.service') < reset
    assert commands.index('systemctl stop coc_web.service') < reset
    assert commands.index('systemctl start personal_apps_web.service') > ready
    assert commands.index('systemctl start coc_web.service') > ready
    assert head.read_text(encoding='ascii') == NEW_SHA
    assert 'RADAR_BOARD_SHARED_RESULTS=on' in env_file.read_text(encoding='utf-8')
    durable = list((tmp / 'logs').glob('perf3-release-*.log'))
    assert len(durable) == 1 and 'release succeeded' in durable[0].read_text()


@pytest.mark.parametrize('failure, expected', [('npm', 23), ('readiness', 70)])
def test_any_build_or_readiness_failure_preserves_status_and_restores_state(
        release_env, failure, expected):
    _, _, env_file, log, head, count, _ = release_env
    env_file.write_text('UNRELATED=secret\n', encoding='utf-8')
    extra = ({'FAKE_FAIL': 'npm'} if failure == 'npm'
             else {'FAKE_READINESS': 'fail'})
    result = _run(release_env, 'first', **extra)

    assert result.returncode == expected, result.stdout + result.stderr
    commands = log.read_text(encoding='utf-8').splitlines()
    assert head.read_text(encoding='ascii') == OLD_SHA
    for service in ('personal_apps_web', 'coc_web', 'coc_scheduler',
                    'personal_apps_gym_notifier', 'radar_ingest'):
        assert f'systemctl start {service}.service' in commands
    assert 'RADAR_BOARD_SHARED_RESULTS' not in env_file.read_text()
    if failure == 'readiness':
        assert count.read_text(encoding='ascii') == '2'


def test_the_rollback_manifest_names_real_older_code_that_retains_the_revision():
    artifact = json.loads(ROLLBACK.read_text(encoding='utf-8'))
    assert artifact['commit'] == OLD_SHA
    migration = artifact['retained_migration']
    result = subprocess.run(
        ['git', '-c', f'safe.directory={ROOT}', '-C', str(ROOT),
         'cat-file', '-e', f'{OLD_SHA}:{migration}'], capture_output=True)
    assert result.returncode == 0
