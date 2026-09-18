"""`python -m demo.blame_cli`: confirm the new failures `bisect gate` found.

Run inside the **head** worktree, so `demo.blame`/`demo.agent` are head's
own code -- confirmation must react to whatever head's policy actually
does, including the regression under test. `--base-store` is read only,
purely as data for the first-divergence comparison
(`docs/decisions/0019-gate-rule.md`).

Input is a JSON file naming which `(scenario, run_index)` pairs regressed
(`gate/action.py` writes it after comparing the two suites' summaries).
Output is one `attribution.blame_store` document per failure under
`--out/blame/`, plus `--out/failures_result.json` summarizing each one's
blamed step for the orchestrator, which never needs to touch a worktree
again after this call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent_bisect.adapters.tau2 import recording_session
from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir
from agent_bisect.attribution.blame_store import save_blame
from agent_bisect.attribution.search import BlameResult
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader, TapeWriter

from demo.agent import demo_completion
from demo.blame import NewFailure, blame_new_failure
from demo.harness import UNUSED_API_BASE, UNUSED_API_KEY, ledger_for, no_limiter

DEFAULT_SEED = 20260917


def _effect_of(result: BlameResult) -> dict | None:
    """The blamed step's own `StepEffect`, as a plain dict for the PR comment.

    `None` when nothing was blamed -- `gate.action.decisive_step_summary`
    then falls back to reporting the step with no effect numbers rather
    than inventing one.
    """
    if result.blamed_step is None or result.estimate is None:
        return None
    for step_effect in result.estimate.step_effects:
        if step_effect.step == result.blamed_step:
            return {
                "effect": step_effect.effect,
                "ci_low": step_effect.ci_low,
                "ci_high": step_effect.ci_high,
                "n": step_effect.treated.n,
            }
    return None


def _step_identity(reader: TapeReader, run_id: str, blamed_step: int | None) -> dict | None:
    """`{actor, tool_name}` for the blamed step, for the PR comment's label."""
    if blamed_step is None:
        return None
    step = reader.get_step(run_id, blamed_step)
    return {"actor": step.actor, "tool_name": step.tool_name}


def _load_failures(path: Path) -> list[NewFailure]:
    document = json.loads(path.read_text())
    return [
        NewFailure(
            scenario_name=entry["scenario_name"],
            run_index=entry["run_index"],
            head_run_id=entry["head_run_id"],
            base_run_id=entry["base_run_id"],
        )
        for entry in document["failures"]
    ]


def run_blame_cli(
    *, failures_path: Path, head_store_dir: Path, base_store_dir: Path, out_dir: Path, seed: int
) -> list[dict]:
    ensure_tau2_data_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    head_store = BlobStore(head_store_dir)
    head_tape = TapeWriter(head_store_dir)
    head_reader = TapeReader(head_store_dir)
    base_store = BlobStore(base_store_dir)
    base_reader = TapeReader(base_store_dir)

    failures = _load_failures(failures_path)
    summaries: list[dict] = []
    with recording_session(
        ledger=ledger_for(out_dir), phase="gate", completion_fn=demo_completion,
        api_key=UNUSED_API_KEY, api_base=UNUSED_API_BASE, limiter_for=no_limiter,
    ):
        for failure in failures:
            result = blame_new_failure(
                failure,
                head_store=head_store, head_reader=head_reader, head_tape=head_tape,
                base_store=base_store, base_reader=base_reader,
                seed=seed,
            )
            save_blame(out_dir, result)
            summaries.append(
                {
                    "scenario_name": failure.scenario_name,
                    "run_index": failure.run_index,
                    "head_run_id": failure.head_run_id,
                    "blamed_step": result.blamed_step,
                    "total_calls": result.total_calls,
                    "effect": _effect_of(result),
                    "step": _step_identity(head_reader, failure.head_run_id, result.blamed_step),
                }
            )
    return summaries


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--failures", type=Path, required=True)
    parser.add_argument("--head-store", type=Path, required=True)
    parser.add_argument("--base-store", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    summaries = run_blame_cli(
        failures_path=args.failures, head_store_dir=args.head_store,
        base_store_dir=args.base_store, out_dir=args.out, seed=args.seed,
    )
    result_path = args.out / "failures_result.json"
    result_path.write_text(json.dumps(summaries, indent=2))
    print(json.dumps(summaries, indent=2))  # noqa: T201 - this IS the CLI's output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
