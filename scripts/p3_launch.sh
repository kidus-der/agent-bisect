#!/usr/bin/env bash
# Launch the P3 planted-fault collection, detached and sharded.
#
# `docs/decisions/0017-p3-collection-policy.md`: every task cheapest-to-score
# first, 10 hours of wall-clock, stop at 120 kept items but never below 60,
# one shared ledger with a hard cap.
#
# Sharding is by PROCESS, not by thread, and that is not a preference:
# `adapters/tau2_replay._completion_patched` rebinds a module-level symbol, so
# two forks in two threads of one process would race and serve each other's
# tapes. Separate processes have separate module state. The tape (SQLite WAL),
# the blob store (atomic writes), the journal (one small file per key) and the
# ledger (a single guarded INSERT) are all built for concurrent writers, and
# the shards share all four — so the stop rule sees the whole dataset, not one
# worker's share.
#
# Resumable: re-running this script skips everything that already has a
# checkpoint. Safe to run again after a crash, a reboot, or a relaunch at a
# different shard count.
#
#   scripts/p3_launch.sh [SHARDS] [MAX_HOURS]

set -euo pipefail

SHARDS="${1:-6}"
MAX_HOURS="${2:-10}"
TARGET="${TARGET:-120}"
FLOOR="${FLOOR:-60}"
MAX_CALLS="${MAX_CALLS:-70000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"
mkdir -p runs/logs runs/p3

echo "P3 collection: ${SHARDS} shards, ${MAX_HOURS} h, target ${TARGET} (floor ${FLOOR})"

for shard in $(seq 0 $((SHARDS - 1))); do
  nohup uv run python -m agent_bisect.cli inject collect \
    --all-tasks \
    --shard "${shard}" \
    --shards "${SHARDS}" \
    --max-hours "${MAX_HOURS}" \
    --target "${TARGET}" \
    --floor "${FLOOR}" \
    --max-calls "${MAX_CALLS}" \
    --phase P3 \
    --runs-dir runs \
    --work-dir runs/p3 \
    >> "runs/logs/p3_collect_${shard}.log" 2>&1 &
  echo "  shard ${shard} -> pid $! (runs/logs/p3_collect_${shard}.log)"
  # Stagger the starts: six processes importing tau2 and litellm at once
  # thrash the page cache for no benefit.
  sleep 3
done

echo "started. progress: runs/p3/status.json; funnel: bisect inject status --work-dir runs/p3"
