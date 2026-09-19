#!/usr/bin/env bash
# Keep the P3 collection alive until the stop rule says otherwise — and stop,
# loudly, when continuing is pointless.
#
# The collection is resumable by construction: every finished unit has a
# checkpoint under `runs/p3/`, and a restart skips it. So the safe response to
# a crash, a hang, or a machine that slept is to start it again. Two things
# are NOT safe, and both have happened here:
#
#   * a run that looks alive while making no progress — a wedged provider
#     connection produces exactly that, and a process check misses it. This
#     watches the status file's own checkpoint clock.
#   * relaunching into a decision. A spent budget or a rejected key makes the
#     collection exit cleanly in seconds, every time, for ever. That loop ran
#     for hours before anyone noticed, so those states are terminal here and
#     are written to the status file rather than left in a log.
#
# It stops for four reasons and names which: the stop rule fired, a human
# wrote `runs/p3/STOP`, a terminal state (budget, auth, or work still parked
# after three un-park passes), or three crashes inside ten minutes.
#
#   scripts/supervise_p3.sh [CONCURRENCY] [MAX_HOURS]

set -uo pipefail

CONCURRENCY="${1:-16}"
MAX_HOURS="${2:-10}"
TARGET="${TARGET:-120}"
FLOOR="${FLOOR:-60}"
MAX_CALLS="${MAX_CALLS:-150000}"
# No checkpoint for this long means wedged, not slow.
STALL_SECONDS="${STALL_SECONDS:-1200}"
# A run that ends with work parked gets this long for the provider to
# recover, then one un-park pass. Three of those and it is not weather.
UNPARK_WAIT="${UNPARK_WAIT:-600}"
UNPARK_LIMIT="${UNPARK_LIMIT:-3}"
CRASH_WINDOW=600
CRASH_LIMIT=3

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p runs/logs runs/p3

STATUS=runs/p3/status.json
LOG=runs/logs/p3_collect_0.log
SUPERVISOR_LOG=runs/logs/p3_supervisor.log
unparks=0
crashes=0
crash_since=0

note() { echo "$(date '+%H:%M:%S') supervisor: $*" | tee -a "$SUPERVISOR_LOG"; }

status_field() {
  python3 -c "
import json
try:
    print(json.load(open('$STATUS')).get('$1') or '')
except Exception:
    print('')
" 2>/dev/null
}

checkpoint_age() {
  python3 -c "
import json, time
from datetime import datetime
try:
    status = json.load(open('$STATUS'))
    stamp = status.get('last_checkpoint_at') or status.get('started_at')
    print(int(time.time() - datetime.fromisoformat(stamp).timestamp()))
except Exception:
    print(0)
" 2>/dev/null
}

give_up() {
  # Terminal, and said out loud: a supervisor that stops quietly is how a
  # relaunch loop runs for hours with nobody watching.
  note "TERMINAL: $1"
  python3 - "$1" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, ".")
from agent_bisect.core.job_status import failed, write_status

write_status(
    Path("runs"),
    failed(kind="inject", phase="P3", label="planted-fault collection", error=sys.argv[1]),
)
PY
  exit 1
}

note "starting: ${CONCURRENCY} in flight, ${MAX_HOURS} h, target ${TARGET} (floor ${FLOOR}), cap ${MAX_CALLS}"

while true; do
  if [ -f runs/p3/STOP ]; then
    note "runs/p3/STOP present — stopping"
    exit 0
  fi
  if [ "$(status_field state)" = "done" ]; then
    note "collection reported done — stopping"
    exit 0
  fi

  started=$(date +%s)
  uv run python -m agent_bisect.cli inject collect \
    --all-tasks --concurrency "${CONCURRENCY}" --max-hours "${MAX_HOURS}" \
    --target "${TARGET}" --floor "${FLOOR}" --max-calls "${MAX_CALLS}" \
    --phase P3 --runs-dir runs --work-dir runs/p3 >> "$LOG" 2>&1 &
  child=$!
  note "launched pid ${child}"

  while kill -0 "$child" 2>/dev/null; do
    sleep 60
    if [ -f runs/p3/STOP ]; then
      note "STOP requested — terminating pid ${child}"
      kill "$child" 2>/dev/null
      wait "$child" 2>/dev/null
      exit 0
    fi
    age=$(checkpoint_age)
    if [ "${age:-0}" -gt "$STALL_SECONDS" ]; then
      note "no checkpoint for ${age}s — restarting (work is resumed, not redone)"
      kill "$child" 2>/dev/null
      wait "$child" 2>/dev/null
      break
    fi
  done
  wait "$child" 2>/dev/null
  code=$?
  ran=$(( $(date +%s) - started ))
  note "pid ${child} exited ${code} after ${ran}s"

  state="$(status_field state)"
  err="$(status_field error)"

  case "$err" in
    *budget*) give_up "budget exhausted — raise --max-calls deliberately, do not relaunch: ${err}" ;;
    *authentication*) give_up "authentication rejected: ${err}" ;;
  esac

  if [ "$state" = "done" ]; then
    note "stop rule reached — stopping"
    exit 0
  fi

  case "$err" in
    *parked*)
      unparks=$(( unparks + 1 ))
      if [ "$unparks" -gt "$UNPARK_LIMIT" ]; then
        give_up "work still parked after ${UNPARK_LIMIT} un-park passes: ${err}"
      fi
      note "parked work (${unparks}/${UNPARK_LIMIT}) — waiting ${UNPARK_WAIT}s, then one un-park pass"
      sleep "$UNPARK_WAIT"
      continue
      ;;
  esac

  if [ "$code" -ne 0 ] && [ "$ran" -lt "$CRASH_WINDOW" ]; then
    now=$(date +%s)
    if [ $(( now - crash_since )) -gt "$CRASH_WINDOW" ]; then
      crashes=0
      crash_since=$now
    fi
    crashes=$(( crashes + 1 ))
    if [ "$crashes" -ge "$CRASH_LIMIT" ]; then
      give_up "${crashes} crashes inside ${CRASH_WINDOW}s; traceback in ${LOG}"
    fi
  fi

  # An exit that was neither terminal nor a crash still gets a pause:
  # relaunching within seconds is how a three-minute loop is built.
  sleep 60
done
