#!/usr/bin/env bash
# Keep the P3 collection alive until the stop rule says otherwise.
#
# The collection is resumable by construction — every finished unit has a
# checkpoint under `runs/p3/` and a restart skips it — so the safe response to
# a crash, a hang, or a machine that went to sleep is simply to start it
# again. What is NOT safe is a run that looks alive while making no progress,
# which is what a wedged provider connection produces: this watches the status
# file's own checkpoint clock and restarts on silence.
#
# It stops for exactly three reasons, and says which:
#   * the collection exited having reached its stop rule (target, budget, or
#     an authentication refusal — all of which are decisions, not faults);
#   * `runs/p3/STOP` exists, so a human said stop;
#   * three crashes inside ten minutes, which is a bug rather than weather.
#
#   scripts/supervise_p3.sh [CONCURRENCY] [MAX_HOURS]

set -uo pipefail

CONCURRENCY="${1:-24}"
MAX_HOURS="${2:-10}"
TARGET="${TARGET:-120}"
FLOOR="${FLOOR:-60}"
MAX_CALLS="${MAX_CALLS:-70000}"
#: No checkpoint for this long means wedged, not slow.
STALL_SECONDS="${STALL_SECONDS:-1200}"
CRASH_WINDOW=600
CRASH_LIMIT=3

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p runs/logs runs/p3

STATUS=runs/p3/status.json
LOG=runs/logs/p3_collect_0.log
SUPERVISOR_LOG=runs/logs/p3_supervisor.log
crashes=()

note() { echo "$(date '+%H:%M:%S') supervisor: $*" | tee -a "$SUPERVISOR_LOG"; }

finished() {
  # `done` is the collection's own word for "the stop rule fired".
  [ -f "$STATUS" ] && python3 -c "
import json,sys
try: sys.exit(0 if json.load(open('$STATUS'))['state'] == 'done' else 1)
except Exception: sys.exit(1)
"
}

checkpoint_age() {
  python3 -c "
import json, time, sys
try:
    from datetime import datetime
    s = json.load(open('$STATUS'))
    stamp = s.get('last_checkpoint_at') or s.get('started_at')
    print(int(time.time() - datetime.fromisoformat(stamp).timestamp()))
except Exception:
    print(0)
"
}

note "starting: ${CONCURRENCY} in flight, ${MAX_HOURS} h, target ${TARGET} (floor ${FLOOR})"

while true; do
  if [ -f runs/p3/STOP ]; then
    note "runs/p3/STOP present — stopping"
    exit 0
  fi
  if finished; then
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

  # Watch it: exit, or a checkpoint clock that stops moving.
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
      note "no checkpoint for ${age}s — restarting pid ${child} (work is resumed, not redone)"
      kill "$child" 2>/dev/null
      wait "$child" 2>/dev/null
      break
    fi
  done
  wait "$child" 2>/dev/null
  code=$?
  ran=$(( $(date +%s) - started ))
  note "pid ${child} exited ${code} after ${ran}s"

  if [ "$code" -ne 0 ] && [ "$ran" -lt "$CRASH_WINDOW" ]; then
    crashes+=("$(date +%s)")
    recent=0
    for t in "${crashes[@]}"; do
      [ $(( $(date +%s) - t )) -lt "$CRASH_WINDOW" ] && recent=$(( recent + 1 ))
    done
    if [ "$recent" -ge "$CRASH_LIMIT" ]; then
      note "${recent} crashes inside ${CRASH_WINDOW}s — this is a bug, not weather; stopping"
      python3 - <<PY
from pathlib import Path
import sys
sys.path.insert(0, "$ROOT")
from agent_bisect.core.job_status import failed, write_status
write_status(Path("runs"), failed(
    kind="inject", phase="P3", label="planted-fault collection",
    error="${recent} crashes inside ${CRASH_WINDOW}s; traceback in $LOG",
))
PY
      exit 1
    fi
  fi
  sleep 10
done
