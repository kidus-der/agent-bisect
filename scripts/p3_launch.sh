#!/usr/bin/env bash
# Launch the P3 planted-fault collection, detached and sharded.
#
# `docs/decisions/0017-p3-collection-policy.md`: every task cheapest-to-score
# first, 10 hours of wall-clock, stop at 120 kept items but never below 60,
# one shared ledger with a hard cap.
#
# Concurrency is threads inside ONE process, and the count of processes is not
# a free parameter: the rate limiter is a process-wide token bucket, so N
# processes permit N times the measured per-model ceiling. Three of them at
# 108 rpm asked for 324 rpm against a 120 rpm limit and earned 325 HTTP 429s
# in three hours. One process makes the limiter mean what `config/limits.toml`
# says it means.
#
# Threads are safe here because the replay seam dispatches per thread through
# a ContextVar (fee9740); before that fix it rebound a module-level symbol and
# two forks served each other's tapes. Sharding across processes remains
# possible — the tape (SQLite WAL), the blob store (atomic writes), the
# journal (one file per key) and the ledger (a guarded INSERT) are all built
# for concurrent writers — but only if the per-process limiter is divided by
# the shard count first.
#
# Resumable: re-running this script skips everything that already has a
# checkpoint. Safe to run again after a crash, a reboot, or a relaunch at a
# different shard count.
#
#   scripts/p3_launch.sh [SHARDS] [MAX_HOURS] [CONCURRENCY_PER_SHARD]

set -euo pipefail

SHARDS="${1:-1}"
MAX_HOURS="${2:-10}"
CONCURRENCY="${3:-24}"
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
