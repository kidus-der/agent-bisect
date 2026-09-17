#!/usr/bin/env python3
"""P1 offline gate: the two P1 criteria that need zero network access.

From `docs/decisions/0001-preregistration.md`'s P1 gate:
  "restoring any step reproduces its recorded DB hash at 100% of steps;
   a redaction test proves the key appears in no blob or log."

This script checks exactly those two things, against real tau2
environments (airline, and retail if it loads) and a synthetic key run
through the tape/blob-store pipeline -- no LLM calls, no network. It does
NOT check the other half of the P1 gate ("20 recorded runs"), which needs
real recordings from the live recorder and is a separate, later script.

Exit code is 0 iff every criterion below prints PASS.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir

ensure_tau2_data_dir()

from agent_bisect.adapters.tau2_snapshot_check import (  # noqa: E402
    AIRLINE_CALLS,
    RETAIL_CALLS,
    check_round_trip,
    run_scripted_sequence,
)
from agent_bisect.core.redaction_check import (  # noqa: E402
    key_absent_everywhere,
    record_run_with_key_everywhere,
)

_KEY_PREFIX = "nvapi" + "-"
_SYNTHETIC_KEY = _KEY_PREFIX + "A" * 64


def _check_snapshot_round_trip(domain: str, calls, environment_factory) -> bool:
    live_env = environment_factory()
    steps = run_scripted_sequence(live_env, calls)
    result = check_round_trip(domain, steps, environment_factory)

    pct = 100.0 * result.reproduced / result.total_steps if result.total_steps else 0.0
    status = "PASS" if result.all_reproduced else "FAIL"
    print(
        f"[{status}] snapshot round trip ({domain}): "
        f"{result.reproduced}/{result.total_steps} steps reproduced ({pct:.1f}%)"
    )
    for failure in result.failures:
        print(f"         - {failure}")
    return result.all_reproduced


def _check_redaction() -> bool:
    tmp_root = Path(tempfile.mkdtemp(prefix="bisect-p1-redaction-"))
    try:
        record_run_with_key_everywhere(tmp_root, _SYNTHETIC_KEY)
        passed, detail = key_absent_everywhere(tmp_root, _SYNTHETIC_KEY)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    status = "PASS" if passed else "FAIL"
    detail_suffix = "" if passed else f": {detail}"
    print(f"[{status}] redaction: synthetic key found in no blob or SQLite index{detail_suffix}")
    return passed


def main() -> int:
    from tau2.domains.airline.environment import get_environment as get_airline_environment

    results = [_check_snapshot_round_trip("airline", AIRLINE_CALLS, get_airline_environment)]

    try:
        from tau2.domains.retail.environment import get_environment as get_retail_environment
    except ImportError:
        print("[SKIP] snapshot round trip (retail): retail domain did not load")
    else:
        results.append(_check_snapshot_round_trip("retail", RETAIL_CALLS, get_retail_environment))

    results.append(_check_redaction())

    all_passed = all(results)
    print(f"\n{'PASS' if all_passed else 'FAIL'}: P1 offline gate")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
