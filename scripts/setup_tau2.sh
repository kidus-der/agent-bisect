#!/usr/bin/env bash
# Shallow-clone tau2-bench (sierra-research/tau2-bench, MIT) at a pinned commit
# into vendor/tau2-bench/ (git-ignored). Idempotent: re-running when the
# vendored checkout is already at the pinned SHA is a no-op.
#
# Rationale for the pin and the shallow-fetch-by-SHA approach:
# docs/decisions/0003-tau2-pin.md
set -euo pipefail

TAU2_SHA="2174a603f6d014ef94473ffa95957f6ce27100db"
TAU2_REPO="https://github.com/sierra-research/tau2-bench.git"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${REPO_ROOT}/vendor/tau2-bench"

if [ -d "${VENDOR_DIR}/.git" ]; then
  current_sha="$(git -C "${VENDOR_DIR}" rev-parse HEAD)"
  if [ "${current_sha}" = "${TAU2_SHA}" ]; then
    echo "tau2-bench already at pinned SHA ${TAU2_SHA}"
    exit 0
  fi
  echo "tau2-bench present at ${current_sha}, re-pinning to ${TAU2_SHA}"
  rm -rf "${VENDOR_DIR}"
fi

mkdir -p "$(dirname "${VENDOR_DIR}")"
git init -q "${VENDOR_DIR}"
git -C "${VENDOR_DIR}" remote add origin "${TAU2_REPO}"
git -C "${VENDOR_DIR}" fetch --depth 1 origin "${TAU2_SHA}"
git -C "${VENDOR_DIR}" checkout -q FETCH_HEAD

echo "tau2-bench checked out at ${TAU2_SHA} into ${VENDOR_DIR}"
