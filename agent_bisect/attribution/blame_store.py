"""Blame results on disk, in the shape the dashboard's real repository reads.

One JSON document per `(run_id, method)` under `<runs>/blame/`:

    runs/blame/<run_id>.json                  # the primary method, "bisect"
    runs/blame/<run_id>.<method>.json         # each baseline that ran

Field names mirror `agent_bisect.server.schemas_runs` exactly —
`RunEstimateView`, `StepEffectView`, `ArmResultView`, `EstimatorConfig`,
`RerunRow`, `JudgePanel`, `JudgeRankEntry` — so the repository reshapes
nothing and re-derives no statistic. Anything the server has no field for
(the interventions actually applied, the suspects that could not be
tested, the judge's parse failure) is carried beside them rather than
folded into one of them.

Writes are atomic (write a sibling temp file, then `replace`) and the JSON
is sorted and indented, so two runs of the same evaluation produce
byte-identical files — which is what `make reproduce` checks.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agent_bisect.attribution.estimate import RunEstimate, StepEffect
from agent_bisect.attribution.judge_view import JudgeVerdict
from agent_bisect.attribution.search import BlameConfig, BlameResult, RerunRecord

#: Bumped when the document's shape changes in a way a reader must notice.
BLAME_SCHEMA_VERSION = 1

BLAME_DIRNAME = "blame"
PRIMARY_METHOD = "bisect"


def blame_dir(root: Path) -> Path:
    return root / BLAME_DIRNAME


def blame_path(root: Path, run_id: str, method: str = PRIMARY_METHOD) -> Path:
    suffix = "" if method == PRIMARY_METHOD else f".{method}"
    return blame_dir(root) / f"{run_id}{suffix}.json"


def _config_document(config: BlameConfig) -> dict[str, Any]:
    """`server.schemas_runs.EstimatorConfig`, taken from the instance used."""
    sequential = config.sequential
    return {
        "delta": sequential.delta,
        "batch": sequential.batch,
        "max_n": sequential.max_n,
        "conf": sequential.conf,
        "efficacy_boundary": sequential.efficacy_boundary,
        "control_mode": config.control_mode,
        "shortlist_m": config.top_m,
    }


def _effect_document(effect: StepEffect) -> dict[str, Any]:
    return {
        "step": effect.step,
        "treated": {"successes": effect.treated.successes, "n": effect.treated.n},
        "control": None
        if effect.control is None
        else {"successes": effect.control.successes, "n": effect.control.n},
        "effect": effect.effect,
        "ci_low": effect.ci_low,
        "ci_high": effect.ci_high,
        "n_batches": effect.n_batches,
        "stop_reason": effect.stop_reason,
        # Not in the server DTO, but the only record of the level the blame
        # decision was actually taken at (docs/decisions/0008-*).
        "decision_conf": effect.decision_conf,
        "decision_ci_low": effect.decision_ci_low,
    }


def _estimate_document(
    estimate: RunEstimate | None, config: BlameConfig
) -> dict[str, Any] | None:
    if estimate is None:
        return None
    return {
        "step_effects": [_effect_document(effect) for effect in estimate.step_effects],
        "blamed_step": estimate.blamed_step,
        "control_mode": estimate.control_mode,
        "control_fork_step": estimate.control_fork_step,
        "treated_reruns": estimate.treated_reruns,
        "control_reruns": estimate.control_reruns,
        "sampler_calls": estimate.sampler_calls,
        "config": _config_document(config),
    }


def _rerun_document(record: RerunRecord) -> dict[str, Any]:
    return {
        "rerun_id": record.rerun_id,
        "arm": record.arm,
        "step": record.step,
        "seed": record.seed,
        "passed": record.passed,
        "n_steps": record.n_steps,
        "calls": record.calls,
        "unguarded_calls": record.unguarded_calls,
    }


def _ranking_document(verdict: JudgeVerdict | None) -> list[dict[str, Any]]:
    if verdict is None:
        return []
    return [
        {
            "step": entry.step,
            "rank": entry.rank,
            "score": entry.score,
            "rationale": entry.rationale,
        }
        for entry in verdict.ranking
    ]


def blame_document(
    result: BlameResult, step_by_step: JudgeVerdict | None = None
) -> dict[str, Any]:
    """The JSON document for one `(run, method)` result."""
    return {
        "schema_version": BLAME_SCHEMA_VERSION,
        "item_id": result.item_id,
        "run_id": result.run_id,
        "method": result.method,
        "blamed_step": result.blamed_step,
        "estimate": _estimate_document(result.estimate, result.config),
        "reruns": [_rerun_document(record) for record in result.reruns],
        "judge": {
            "all_at_once": _ranking_document(result.judge),
            "step_by_step": _ranking_document(step_by_step),
        },
        "judge_rationale": result.judge.rationale,
        "judge_parse_failed": result.judge.parse_failed,
        "judge_failure_reason": result.judge.failure_reason,
        "shortlist": list(result.shortlist),
        "tested_steps": list(result.tested_steps),
        "interventions": {str(step): name for step, name in result.interventions.items()},
        "untestable": list(result.untestable),
        "cost": {
            "judge_calls": result.judge_calls,
            "replay_calls": result.replay_calls,
            "total_calls": result.total_calls,
        },
        # Non-zero only for the re-run-live baseline, whose prefix drifts by
        # construction. A Bisect result with this above 0 is a bug, and
        # `scripts/gates/p5.py` refuses one.
        "unguarded_calls": result.unguarded_calls,
    }


def save_blame(
    root: Path, result: BlameResult, step_by_step: JudgeVerdict | None = None
) -> Path:
    """Write one result atomically and return where it landed."""
    path = blame_path(root, result.run_id, result.method)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        blame_document(result, step_by_step), indent=2, sort_keys=True, ensure_ascii=False
    )
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(payload + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def load_blame(root: Path, run_id: str, method: str = PRIMARY_METHOD) -> dict[str, Any]:
    """Read one result back. Raises `FileNotFoundError` if it was never written."""
    path = blame_path(root, run_id, method)
    if not path.exists():
        raise FileNotFoundError(f"no {method!r} blame result for run {run_id!r} under {root}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_blamed_runs(root: Path) -> tuple[str, ...]:
    """Every run with a primary (`bisect`) result, in sorted order."""
    directory = blame_dir(root)
    if not directory.is_dir():
        return ()
    return tuple(
        sorted(
            path.stem
            for path in directory.glob("*.json")
            if "." not in path.stem and not path.name.endswith(".tmp")
        )
    )


def load_all(root: Path, methods: Sequence[str]) -> dict[tuple[str, str], dict[str, Any]]:
    """Every stored result for `methods`, keyed by `(run_id, method)`."""
    results: dict[tuple[str, str], dict[str, Any]] = {}
    for run_id in list_blamed_runs(root):
        for method in methods:
            try:
                results[(run_id, method)] = load_blame(root, run_id, method)
            except FileNotFoundError:
                continue
    return results
