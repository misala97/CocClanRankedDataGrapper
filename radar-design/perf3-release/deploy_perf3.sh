#!/usr/bin/env bash
# Proposed PERF3 release runner. REVIEW LOCALLY; DO NOT EXECUTE WITHOUT RELEASE
# APPROVAL. It changes the target checkout, schema, .env and systemd services.
set -Eeuo pipefail

MODE=${1:-}
CANDIDATE=${2:-}
case "$MODE" in first|routine) ;; *) echo 'usage: deploy_perf3.sh first|routine FULL_SHA' >&2; exit 64;; esac
case "$CANDIDATE" in [0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;; *) echo 'FULL_SHA must be 40 lowercase hex characters' >&2; exit 64;; esac

REPO=${PERF3_REPO:-/root/coc-stats}
APP="$REPO/personal_apps"
ENV_FILE=${PERF3_ENV_FILE:-$REPO/.env}
UNIT_SOURCE=${PERF3_UNIT_SOURCE:-$REPO/radar-design/perf3-release/radar_board_producer.service}
UNIT_TARGET=${PERF3_UNIT_TARGET:-/etc/systemd/system/radar_board_producer.service}
LOG_DIR=${PERF3_LOG_DIR:-/var/log/perf3-release}
SYSTEMCTL=${PERF3_SYSTEMCTL:-systemctl}
GIT=${PERF3_GIT:-git}
NPM=${PERF3_NPM:-npm}
PIP=${PERF3_PIP:-$REPO/venv/bin/pip}
FLASK=${PERF3_FLASK:-$REPO/venv/bin/flask}
PYTHON=${PERF3_PYTHON:-$REPO/venv/bin/python}
ATTEMPTS=${PERF3_READINESS_ATTEMPTS:-180}
INTERVAL=${PERF3_READINESS_INTERVAL:-5}
SERVICES=(personal_apps_web coc_web coc_scheduler personal_apps_gym_notifier radar_ingest radar_board_producer)

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/perf3-release-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "PERF3 release mode=$MODE candidate=$CANDIDATE log=$LOG_FILE"

run() { local command=$1; shift; $command "$@"; }
declare -A ACTIVE ENABLED
for service in "${SERVICES[@]}"; do
  if run "$SYSTEMCTL" is-active "$service.service" >/dev/null 2>&1; then ACTIVE[$service]=active; else ACTIVE[$service]=inactive; fi
  if run "$SYSTEMCTL" is-enabled "$service.service" >/dev/null 2>&1; then ENABLED[$service]=enabled; else ENABLED[$service]=disabled; fi
done
ORIGINAL_SHA=$(run "$GIT" -C "$REPO" rev-parse HEAD)
ORIGINAL_FLAG=$(grep -E '^[[:space:]]*(export[[:space:]]+)?RADAR_BOARD_SHARED_RESULTS=' "$ENV_FILE" || true)
CHANGED=0

set_flag() {
  local value=$1 tmp="$ENV_FILE.perf3.$$"
  awk '!/^[[:space:]]*(export[[:space:]]+)?RADAR_BOARD_SHARED_RESULTS=/' "$ENV_FILE" > "$tmp"
  if [ "$value" != absent ]; then printf 'RADAR_BOARD_SHARED_RESULTS=%s\n' "$value" >> "$tmp"; fi
  chmod --reference="$ENV_FILE" "$tmp" 2>/dev/null || true
  mv "$tmp" "$ENV_FILE"
}

restore_flag() {
  set_flag absent
  if [ -n "$ORIGINAL_FLAG" ]; then printf '%s\n' "$ORIGINAL_FLAG" >> "$ENV_FILE"; fi
}

restore_services() {
  local allow_web=$1
  for service in "${SERVICES[@]}"; do
    if [[ "$service" == personal_apps_web || "$service" == coc_web ]] && [ "$allow_web" != yes ]; then
      run "$SYSTEMCTL" stop "$service.service" || true
    elif [ "${ACTIVE[$service]}" = active ]; then
      run "$SYSTEMCTL" start "$service.service" || return 1
    else
      run "$SYSTEMCTL" stop "$service.service" || return 1
    fi
    if [ "${ENABLED[$service]}" = enabled ]; then
      run "$SYSTEMCTL" enable "$service.service" || return 1
    else
      run "$SYSTEMCTL" disable "$service.service" || return 1
    fi
  done
}

rollback_checkout() {
  [ "$CHANGED" = 1 ] || return 0
  echo "restoring checkout $ORIGINAL_SHA"
  run "$GIT" -C "$REPO" reset --hard "$ORIGINAL_SHA" || return 1
  run "$PIP" install -r "$APP/requirements.txt" || return 1
  (cd "$APP" && run "$NPM" ci && run "$NPM" run build) || return 1
  (cd "$APP" && FLASK_APP=app.py run "$FLASK" db upgrade) || return 1
}

on_failure() {
  local status=$1 recovery=yes
  trap - ERR INT TERM
  set +e
  echo "release failed status=$status; restoring captured state"
  restore_flag || recovery=no
  rollback_checkout || recovery=no
  restore_services "$recovery" || recovery=no
  if [ "$recovery" != yes ]; then
    echo 'recovery incomplete; both web units remain stopped'
    run "$SYSTEMCTL" stop personal_apps_web.service || true
    run "$SYSTEMCTL" stop coc_web.service || true
  fi
  echo "failure handling complete recovery=$recovery original_status=$status"
  exit "$status"
}
trap 'on_failure $?' ERR
trap 'on_failure 130' INT TERM
fail_readiness() { return 70; }

# Durable, read-only facts. Environment VALUES are never printed.
run "$GIT" -C "$REPO" status --porcelain
run "$GIT" -C "$REPO" rev-parse HEAD
for service in "${SERVICES[@]}"; do run "$SYSTEMCTL" cat "$service.service" || true; done
grep -oE '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*' "$ENV_FILE" || true
(cd "$APP" && FLASK_APP=app.py run "$FLASK" db current)

if [ "${ACTIVE[personal_apps_web]}" != active ] || [ "${ACTIVE[coc_web]}" != active ]; then
  echo 'both web units must initially be active so restoration is unambiguous' >&2
  false
fi
if [ "$MODE" = first ] && [ -n "$ORIGINAL_FLAG" ] && echo "$ORIGINAL_FLAG" | grep -Eq '=on[[:space:]]*$'; then
  echo 'first rollout requires the flag absent/off' >&2; false
fi
if [ "$MODE" = routine ] && ! echo "$ORIGINAL_FLAG" | grep -Eq '=on[[:space:]]*$'; then
  echo 'routine rollout requires the already-on flag' >&2; false
fi

for service in "${SERVICES[@]}"; do run "$SYSTEMCTL" stop "$service.service"; done
run "$GIT" -C "$REPO" fetch origin
run "$GIT" -C "$REPO" cat-file -e "$CANDIDATE^{commit}"
run "$GIT" -C "$REPO" reset --hard "$CANDIDATE"
CHANGED=1
run "$PIP" install -r "$APP/requirements.txt"
(cd "$APP" && run "$NPM" ci && run "$NPM" run build)
(cd "$APP" && FLASK_APP=app.py run "$FLASK" db upgrade)
(cd "$APP" && FLASK_APP=app.py run "$FLASK" db current)

if [ "$MODE" = first ]; then
  install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
  run "$SYSTEMCTL" daemon-reload
  run "$SYSTEMCTL" enable radar_board_producer.service
fi
run "$SYSTEMCTL" start radar_board_producer.service

ready=no
for ((attempt=1; attempt<=ATTEMPTS; attempt++)); do
  if (cd "$APP" && run "$PYTHON" run_radar_board_producer.py --readiness); then ready=yes; break; fi
  [ "$attempt" -eq "$ATTEMPTS" ] || sleep "$INTERVAL"
done
if [ "$ready" != yes ]; then
  echo "readiness timed out after $ATTEMPTS attempts" >&2
  fail_readiness
fi

set_flag on
if [ "$MODE" = first ]; then ACTIVE[radar_board_producer]=active; ENABLED[radar_board_producer]=enabled; fi
restore_services yes
run "$SYSTEMCTL" is-active personal_apps_web.service
run "$SYSTEMCTL" is-active coc_web.service
run "$SYSTEMCTL" is-active radar_board_producer.service
(cd "$APP" && FLASK_APP=app.py run "$FLASK" db current)
echo "release succeeded candidate=$CANDIDATE"
trap - ERR INT TERM
