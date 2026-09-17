#!/usr/bin/env bash
# Launch the P3 planted-fault collection, detached and sharded.
#
# `docs/decisions/0017-p3-collection-policy.md`: every task cheapest-to-score
# first, 10 hours of wall-clock, stop at 120 kept items but never below 60,
# one shared ledger with a hard cap.
#
# Concurrency is threads inside a few processes. It used to have to be
# processes: `adapters/tau2_replay._completion_patched` rebound a module-level
# symbol, so two forks in two threads served each other's tapes. That was fixed
# (a ContextVar dispatcher, fee9740), so one process now runs many tasks at
# once for the cost of one interpreter. A handful of processes rather than one
# is for crash isolation, and because the shards share the tape (SQLite WAL),
# the blob store (atomic writes), the journal (one small file per key) and the
# ledger (a single guarded INSERT) — all built for concurrent writers — the
# stop rule sees the whole dataset, not one worker's share.
#
# Resumable: re-running this script skips everything that already has a
# checkpoint. Safe to run again after a crash, a reboot, or a relaunch at a
# different shard count.
#
#   scripts/p3_launch.sh [SHARDS] [MAX_HOURS] [CONCURRENCY_PER_SHARD]

set -euo pipefail

SHARDS="${1:-3}"
MAX_HOURS="${2:-10}"
CONCURRENCY="${3:-9}"
TARGET="${TARGET:-120}"
FLOOR="${FLOOR:-60}"
MAX_CALLS="${MAX_CALLS:-70000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"
mkdir -p runs/logs runs/p3

echo "P3 collection: ${SHARDS} shards x ${CONCURRENCY} in flight, ${MAX_HOURS} h, "\
     "target ${TARGET} (floor ${FLOOR})"

for shard in $(seq 0 $((SHARDS - 1))); do
  nohup uv run python -m agent_bisect.cli inject collect \
    --all-tasks \
    --shard "${shard}" \
    --shards "${SHARDS}" \
    --concurrency "${CONCURRENCY}" \
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
