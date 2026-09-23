#!/usr/bin/env bash
# Proposed PERF3 release runner. REVIEW LOCALLY; DO NOT EXECUTE WITHOUT RELEASE
# APPROVAL. It changes the target checkout, schema, .env and systemd services.
#
# Recovery model, which is the part worth reading twice:
#
#   Before the candidate migration has been applied, a failure is fully
#   reversible: reset the checkout, reinstall, rebuild, restore services.
#
#   AFTER the candidate migration has been applied, the checkout is NOT rolled
#   back. The additive migration cannot be undone by deploying older code -- old
#   code cannot even resolve the stamp -- so rolling the checkout back would
#   strand the installation. The documented recovery is the one PERF3-RELEASE.md
#   prescribes: the shared flag is explicitly set OFF,
#   the schema is retained, and the candidate code serves its flag-off path,
#   which is the current production behaviour. A full code rollback is a
#   separate, separately authorized step using the prepared compatible artifact
#   radar-design/perf3-release/rollback-compatible.json, which retains
#   migration b7e3f9c1a2d4.
#
#   Once readiness has passed and the flag is on, the release is not rolled back
#   by this script at all. A failure while restoring services is reported per
#   unit and exits 75; it does not undo a release that succeeded.
#
# Constraint: the PERF3_* command variables are word-split on purpose, so the
# test harness can inject "fake systemctl". None of the PERF3_* paths may
# contain whitespace.
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
TIMEOUT=${PERF3_TIMEOUT:-timeout}
DEADLINE_SECONDS=${PERF3_READINESS_SECONDS:-900}
PROBE_SECONDS=${PERF3_PROBE_SECONDS:-30}
ATTEMPTS=${PERF3_READINESS_ATTEMPTS:-180}
INTERVAL=${PERF3_READINESS_INTERVAL:-5}
for path in "$REPO" "$ENV_FILE" "$UNIT_SOURCE" "$UNIT_TARGET" "$LOG_DIR"; do
  if [[ "$path" =~ [[:space:]] ]]; then echo 'PERF3 paths must not contain whitespace' >&2; exit 64; fi
done
for count in "$DEADLINE_SECONDS" "$PROBE_SECONDS" "$ATTEMPTS"; do
  if ! [[ "$count" =~ ^[1-9][0-9]*$ ]]; then echo 'readiness bounds must be positive integers' >&2; exit 64; fi
done
if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]]; then echo 'readiness interval must be a nonnegative integer' >&2; exit 64; fi
SERVICES=(personal_apps_web coc_web coc_scheduler personal_apps_gym_notifier radar_ingest radar_board_producer)
WEB_SERVICES=(personal_apps_web coc_web)

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/perf3-release-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
# Keep the writer's pid so the durable log is complete before this script exits:
# bash does not wait for a process substitution, and the last lines written here
# are exactly the ones a post-mortem needs.
exec > >(tee -a "$LOG_FILE"); TEE_PID=$!
exec 2>&1
echo "PERF3 release mode=$MODE candidate=$CANDIDATE log=$LOG_FILE"

run() { local command=$1; shift; $command "$@"; }

declare -A ACTIVE ENABLED EXISTS
for service in "${SERVICES[@]}"; do
  load=$(run "$SYSTEMCTL" show "$service.service" --property=LoadState --value)
  if [ "$load" = not-found ]; then EXISTS[$service]=no; else EXISTS[$service]=yes; fi
  if run "$SYSTEMCTL" is-active "$service.service" >/dev/null 2>&1; then ACTIVE[$service]=active; else ACTIVE[$service]=inactive; fi
  if run "$SYSTEMCTL" is-enabled "$service.service" >/dev/null 2>&1; then ENABLED[$service]=enabled; else ENABLED[$service]=disabled; fi
done
ORIGINAL_SHA=$(run "$GIT" -C "$REPO" rev-parse HEAD)
ORIGINAL_FLAG=$(grep -E '^[[:space:]]*(export[[:space:]]+)?RADAR_BOARD_SHARED_RESULTS=' "$ENV_FILE" || true)
# Phase flags. Each one says what a failure from here on may and may not undo.
STOPPED=0
CHANGED=0        # the checkout has been touched
MIGRATION_PHASE=not_attempted # attempted includes partial or unknown DDL
UNIT_INSTALLED=0 # this run installed the producer unit file
ACTIVATED=0      # readiness passed and the flag was set: never roll the release back

set_flag() {
  # Rewrite .env without ever handing back a truncated secrets file: awk's exit
  # status is checked, the surviving line count is compared against the
  # original, and only then is the replacement moved into place.
  local value=$1 tmp="$ENV_FILE.perf3.$$" before after expected
  before=$(wc -l < "$ENV_FILE")
  expected=$(grep -cE '^[[:space:]]*(export[[:space:]]+)?RADAR_BOARD_SHARED_RESULTS=' "$ENV_FILE" || true)
  if ! awk '!/^[[:space:]]*(export[[:space:]]+)?RADAR_BOARD_SHARED_RESULTS=/' "$ENV_FILE" > "$tmp"; then
    echo "refusing to replace $ENV_FILE: awk failed" >&2; rm -f "$tmp"; return 1
  fi
  after=$(wc -l < "$tmp")
  if [ "$after" -ne "$((before - expected))" ]; then
    echo "refusing to replace $ENV_FILE: $after lines kept, expected $((before - expected))" >&2
    rm -f "$tmp"; return 1
  fi
  if [ "$value" != absent ]; then
    # Preserve the original line's `export ` form, so a file that relied on it
    # keeps working for shell consumers.
    if printf '%s' "$ORIGINAL_FLAG" | grep -Eq '^[[:space:]]*export[[:space:]]'; then
      printf 'export RADAR_BOARD_SHARED_RESULTS=%s\n' "$value" >> "$tmp" || { rm -f "$tmp"; return 1; }
    else
      printf 'RADAR_BOARD_SHARED_RESULTS=%s\n' "$value" >> "$tmp" || { rm -f "$tmp"; return 1; }
    fi
  fi
  # A secrets file must not widen to the umask. Failing to copy the mode is a
  # refusal, not a shrug.
  chmod --reference="$ENV_FILE" "$tmp" || { echo "refusing to replace $ENV_FILE: cannot copy its mode" >&2; rm -f "$tmp"; return 1; }
  mv "$tmp" "$ENV_FILE" || { rm -f "$tmp"; return 1; }
}

restore_flag() {
  local status=0
  set_flag absent || status=1
  if [ -n "$ORIGINAL_FLAG" ]; then printf '%s\n' "$ORIGINAL_FLAG" >> "$ENV_FILE" || status=1; fi
  return "$status"
}

stop_webs() {
  for service in "${WEB_SERVICES[@]}"; do run "$SYSTEMCTL" stop "$service.service" || true; done
}

# Restore every captured service state. It does NOT stop at the first failure:
# abandoning the remaining units is how a partial failure becomes a total
# outage. Every unit is reported, and the function fails at the end if any did.
restore_services() {
  local allow_web=$1 status=0 wanted
  for service in "${SERVICES[@]}"; do
    if [ "${EXISTS[$service]}" = no ]; then continue; fi
    if [[ " ${WEB_SERVICES[*]} " == *" $service "* ]] && [ "$allow_web" != yes ]; then
      run "$SYSTEMCTL" stop "$service.service" || true
      echo "restore: $service left stopped (web held down)"
      continue
    fi
    wanted=${ACTIVE[$service]}
    if [ "$wanted" = active ]; then
      if run "$SYSTEMCTL" start "$service.service"; then echo "restore: $service started"; else echo "restore: $service FAILED to start" >&2; status=1; fi
    else
      if run "$SYSTEMCTL" stop "$service.service"; then echo "restore: $service stopped"; else echo "restore: $service FAILED to stop" >&2; status=1; fi
    fi
    if [ "${ENABLED[$service]}" = enabled ]; then
      run "$SYSTEMCTL" enable "$service.service" || { echo "restore: $service FAILED to enable" >&2; status=1; }
    else
      run "$SYSTEMCTL" disable "$service.service" || { echo "restore: $service FAILED to disable" >&2; status=1; }
    fi
  done
  return "$status"
}

remove_installed_unit() {
  [ "$UNIT_INSTALLED" = 1 ] || return 0
  rm -f "$UNIT_TARGET" || return 1
  run "$SYSTEMCTL" daemon-reload || return 1
  EXISTS[radar_board_producer]=no
  echo "removed the producer unit this run installed"
}

# Only ever called before any migration attempt. See the recovery model at the top.
rollback_checkout() {
  [ "$CHANGED" = 1 ] || return 0
  echo "restoring checkout $ORIGINAL_SHA (migration not applied, so this is reversible)"
  run "$GIT" -C "$REPO" reset --hard "$ORIGINAL_SHA" || return 1
  run "$PIP" install -r "$REPO/requirements.txt" || return 1
  (cd "$APP" && run "$NPM" ci && run "$NPM" run build) || return 1
}

on_failure() {
  local status=$1 recovery=yes
  trap - ERR INT TERM
  set +e
  if [ "$ACTIVATED" = 1 ]; then
    echo "activation degraded original_status=$status; candidate and ON flag retained; inspect service health"
    exit 75
  fi
  echo "release failed status=$status migration_phase=$MIGRATION_PHASE"
  if [ "$CHANGED" = 0 ] && [ "$STOPPED" = 0 ]; then
    echo 'preflight failed before checkout; captured service/flag state left unchanged'
    exit "$status"
  fi
  stop_webs
  if [ "${EXISTS[radar_board_producer]}" = yes ]; then
    run "$SYSTEMCTL" stop radar_board_producer.service || recovery=no
  fi
  if [ "$MIGRATION_PHASE" = attempted ]; then
    echo 'migration incomplete or unknown: ALL stopped consumers remain stopped; follow manual recovery before any restart'
    exit "$status"
  elif [ "$MIGRATION_PHASE" = completed ]; then
    set_flag off || recovery=no
    ACTIVE[radar_board_producer]=inactive
    echo 'candidate schema retained; recovery explicitly flag OFF; producer stopped'
  else
    restore_flag || recovery=no
    rollback_checkout || recovery=no
    remove_installed_unit || recovery=no
  fi
  restore_services "$recovery" || recovery=no
  if [ "$recovery" != yes ]; then
    echo 'recovery incomplete; both web units remain stopped'
    stop_webs
  fi
  echo "failure handling complete recovery=$recovery original_status=$status"
  exit "$status"
}
trap 'on_failure $?' ERR
trap 'on_failure 130' INT TERM
fail_readiness() { return 70; }

# Only allowlisted non-secret systemd properties; never print unit contents,
# Environment, ExecStart or continuation lines from configuration files.
run "$GIT" -C "$REPO" status --porcelain
run "$GIT" -C "$REPO" rev-parse HEAD
for service in "${SERVICES[@]}"; do
  run "$SYSTEMCTL" show "$service.service" --property=LoadState,ActiveState,UnitFileState || true
done
grep -oE '^[[:space:]]*(export[[:space:]]+)?[A-Za-z_][A-Za-z0-9_]*' "$ENV_FILE" || true
(cd "$APP" && FLASK_APP=app.py run "$FLASK" db current)

if [ "${ACTIVE[personal_apps_web]}" != active ] || [ "${ACTIVE[coc_web]}" != active ]; then
  echo 'both web units must initially be active so restoration is unambiguous' >&2
  false
fi
# Fail CLOSED on anything that looks like an already-on flag, including quoted
# and uppercase spellings, rather than only the exact lowercase bare word.
if [ "$MODE" = first ] && [ -n "$ORIGINAL_FLAG" ] && printf '%s' "$ORIGINAL_FLAG" | grep -Eiq "=[[:space:]]*[\"']?(on|true|1|yes)[\"']?[[:space:]]*$"; then
  echo 'first rollout requires the flag absent/off' >&2; false
fi
if [ "$MODE" = routine ] && ! printf '%s' "$ORIGINAL_FLAG" | grep -Eq '=on[[:space:]]*$'; then
  echo 'routine rollout requires the already-on flag' >&2; false
fi

STOPPED=1
for service in "${SERVICES[@]}"; do
  if [ "${EXISTS[$service]}" = yes ]; then run "$SYSTEMCTL" stop "$service.service"; fi
done
run "$GIT" -C "$REPO" fetch origin
run "$GIT" -C "$REPO" cat-file -e "$CANDIDATE^{commit}"
# Set BEFORE the reset: a reset that fails partway has still touched the tree,
# and recovery must know that.
CHANGED=1
run "$GIT" -C "$REPO" reset --hard "$CANDIDATE"
run "$PIP" install -r "$REPO/requirements.txt"
(cd "$APP" && run "$NPM" ci && run "$NPM" run build)
# Set BEFORE the upgrade: a migration interrupted partway has still applied DDL
# on MariaDB, which commits each CREATE independently.
MIGRATION_PHASE=attempted
(cd "$REPO/coc_stats" && FLASK_APP=app.py run "$FLASK" db upgrade)
(cd "$APP" && FLASK_APP=app.py run "$FLASK" db upgrade)
(cd "$APP" && FLASK_APP=app.py run "$FLASK" db current)
MIGRATION_PHASE=completed

if [ "$MODE" = first ]; then
  install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
  UNIT_INSTALLED=1
  EXISTS[radar_board_producer]=yes
  run "$SYSTEMCTL" daemon-reload
  run "$SYSTEMCTL" enable radar_board_producer.service
fi
run "$SYSTEMCTL" start radar_board_producer.service

ready=no
# GNU timeout kills hung probes. SECONDS bounds the entire readiness phase;
# kill escalation can add at most one second beyond the declared budget.
deadline=$((SECONDS + DEADLINE_SECONDS))
for ((attempt=1; attempt<=ATTEMPTS; attempt++)); do
  remaining=$((deadline - SECONDS))
  [ "$remaining" -gt 0 ] || break
  budget=$PROBE_SECONDS
  [ "$budget" -le "$remaining" ] || budget=$remaining
  if (cd "$APP" && $TIMEOUT --kill-after=1 "${budget}s" $PYTHON run_radar_board_producer.py --readiness); then ready=yes; break; fi
  remaining=$((deadline - SECONDS))
  [ "$remaining" -gt 0 ] || break
  pause=$INTERVAL
  [ "$pause" -le "$remaining" ] || pause=$remaining
  [ "$attempt" -eq "$ATTEMPTS" ] || sleep "$pause"
done
if [ "$ready" != yes ]; then
  echo "readiness timed out: total budget=${DEADLINE_SECONDS}s attempts=$ATTEMPTS" >&2
  fail_readiness
fi

set_flag on
# The producer is intended-active from here in BOTH modes: readiness passed and
# the shared path is about to be served. Restoring it to a captured `inactive`
# would leave the flag on with nothing building.
ACTIVE[radar_board_producer]=active
ENABLED[radar_board_producer]=enabled
ACTIVATED=1
# Past this line the release is not undone. A restoration failure is reported
# per unit and exits 75; it does not trigger the rollback trap.
trap - ERR
if ! restore_services yes; then
  echo 'release activated, but at least one service did not reach its intended state' >&2
  echo 'the flag is ON and the schema is applied; fix the named units by hand' >&2
  trap - INT TERM
  exit 75
fi
trap 'on_failure $?' ERR
run "$SYSTEMCTL" is-active personal_apps_web.service
run "$SYSTEMCTL" is-active coc_web.service
run "$SYSTEMCTL" is-active radar_board_producer.service
(cd "$APP" && FLASK_APP=app.py run "$FLASK" db current)
echo "release succeeded candidate=$CANDIDATE activated=$ACTIVATED"
trap - ERR INT TERM
# Let the durable log's writer drain before the shell exits.
exec 1>&- 2>&-
wait "$TEE_PID" 2>/dev/null || true
