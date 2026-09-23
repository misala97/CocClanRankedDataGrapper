#!/usr/bin/env bash
set -Eeuo pipefail
exec 9>/run/lock/radar-release.lock
flock -n 9 || { echo 'Another release is running' >&2; exit 73; }
/root/backup_db.sh
git -C /root/coc-stats fetch origin
candidate=$(git -C /root/coc-stats rev-parse origin/main)
mkdir -p /root/perf3-release
runner=$(mktemp /root/perf3-release/runner.XXXXXX.sh)
trap 'rm -f "$runner"' EXIT
git -C /root/coc-stats show "$candidate:radar-design/perf3-release/deploy_perf3.sh" > "$runner"
bash -n "$runner"
bash "$runner" routine "$candidate"
