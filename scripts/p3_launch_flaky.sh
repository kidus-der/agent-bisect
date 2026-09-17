#!/usr/bin/env bash
# Launch the flaky-world half of the P3 collection, detached and sharded.
#
# `docs/decisions/0017-p3-collection-policy.md` section 4: airline only, the
# same rules as the plain world, target 30 kept items and a minimum of 20,
# started once the plain collection has 60. It draws on the same ledger cap
# and the same 10-hour budget, and freezes UNSPLIT to
# `data/manifest_flaky.json` because nothing is tuned on it.
#
# Separate work directory, so the two funnels never mix: a flaky item and a
# plain item are not interchangeable and the dataset card reports them apart.
#
#   scripts/p3_launch_flaky.sh [SHARDS] [MAX_HOURS]

set -euo pipefail

SHARDS="${1:-3}"
MAX_HOURS="${2:-4}"
TARGET="${TARGET:-30}"
FLOOR="${FLOOR:-20}"
MAX_CALLS="${MAX_CALLS:-70000}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT"
mkdir -p runs/logs runs/p3-flaky

echo "P3 flaky collection: ${SHARDS} shards, ${MAX_HOURS} h, target ${TARGET} (floor ${FLOOR})"

for shard in $(seq 0 $((SHARDS - 1))); do
  nohup uv run python -m agent_bisect.cli inject collect \
    --domain airline \
    --tasks 0-49 \
    --flaky \
    --shard "${shard}" \
    --shards "${SHARDS}" \
    --max-hours "${MAX_HOURS}" \
    --target "${TARGET}" \
    --floor "${FLOOR}" \
    --max-calls "${MAX_CALLS}" \
    --phase P3 \
    --runs-dir runs \
    --work-dir runs/p3-flaky \
    >> "runs/logs/p3_flaky_${shard}.log" 2>&1 &
  echo "  shard ${shard} -> pid $!"
  sleep 3
done

echo "started. freeze with: bisect inject freeze --work-dir runs/p3-flaky \\"
echo "  --out data/manifest_flaky.json --unsplit"
