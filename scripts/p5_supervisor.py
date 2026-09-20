#!/usr/bin/env python
"""Run `bisect eval` to completion, unattended, and stop for the right reasons.

    uv run python scripts/p5_supervisor.py --split dev [--concurrency 8]

The evaluation is already resumable — a fork whose outcome is on the tape
is reused rather than re-bought, and a judged prompt is served from the
judge store — so the supervisor's whole job is to restart it after a
crash and to *refuse* to restart it when restarting would be wrong.

It stops, and says which, on:

- **success** — the evaluation exited 0;
- **budget** — the P5 ledger reached `--max-calls`, checked before every
  attempt so a restart can never push past the cap;
- **auth** — the provider rejected the credential; retrying spends the
  retry budget on a key that will not start working;
- **stop file** — `runs/p5/STOP` exists, which is how a human stops it
  without killing a process mid-fork;
- **crashes** — `--max-crashes` consecutive non-zero exits (default 3).

Every terminal state is written to `runs/p5/status.json` through
`core.job_status`, which is what the dashboard's Live page reads, and
printed as one line so a supervisor log is greppable.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.job_status import done, failed, running, write_status

PHASE = "P5"
KIND = "eval"
RUNS_DIR = Path("runs")
STOP_FILE = "STOP"
DEFAULT_MAX_CALLS = 80_000
DEFAULT_MAX_CRASHES = 3
#: Seconds between attempts, so a provider wobble is not hammered.
BACKOFF_S = 30.0

#: `bisect eval` exit code for "some item has no verdict". Restartable:
#: everything bought is on the tape, so another attempt resumes cheaply.
INCOMPLETE_EXIT_CODE = 9

#: Substrings that mean "do not restart this".
AUTH_MARKERS = ("AuthenticationError", "credentials rejected", "NVIDIA_API_KEY")
BUDGET_MARKERS = ("BudgetExceededError", "budget exceeded")


@dataclass(frozen=True, slots=True)
class Outcome:
    """Why the supervisor stopped."""

    reason: str
    detail: str
    ok: bool


def stop_file(out_dir: Path) -> Path:
    return out_dir / STOP_FILE


def calls_spent(ledger_path: Path) -> int:
    if not ledger_path.exists():
        return 0
    return BudgetLedger(ledger_path).totals_per_phase().get(PHASE, 0)


def classify(returncode: int, tail: str) -> str | None:
    """`None` when a restart is reasonable, else why it is not."""
    if returncode == 0:
        return None
    if any(marker in tail for marker in AUTH_MARKERS):
        return "auth"
    if any(marker in tail for marker in BUDGET_MARKERS):
        return "budget"
    return None


def _command(args: argparse.Namespace) -> list[str]:
    command = [
        "uv", "run", "bisect", "eval",
        "--split", args.split,
        "--manifest", str(args.manifest),
        "--out-dir", str(args.out_dir),
        "--results-dir", str(args.results_dir),
        "--concurrency", str(args.concurrency),
        "--item-concurrency", str(args.item_concurrency),
        "--top", str(args.top),
        "--n", str(args.n),
        "--seed", str(args.seed),
    ]
    if args.resume:
        command.append("--resume")
    if args.per_step_sensitivity:
        command.append("--per-step-sensitivity")
    return command


def supervise(args: argparse.Namespace) -> Outcome:
    crashes = 0
    attempt = 0
    while True:
        if stop_file(args.out_dir).exists():
            return Outcome("stop_file", f"{stop_file(args.out_dir)} exists", ok=False)
        spent = calls_spent(args.ledger)
        if spent >= args.max_calls:
            return Outcome("budget", f"{spent} P5 calls >= cap {args.max_calls}", ok=False)

        attempt += 1
        started = time.time()
        print(
            f"[supervisor] attempt {attempt} · split {args.split} · "
            f"{spent} P5 calls spent · cap {args.max_calls}",
            flush=True,
        )
        write_status(
            args.out_dir.parent,
            running(kind=KIND, phase=PHASE, items_done=0, items_total=1,
                    calls_spent=spent),
            phase=PHASE,
        )
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            _command(args), capture_output=True, text=True, check=False
        )
        elapsed = time.time() - started
        tail = (result.stdout or "") + (result.stderr or "")
        sys.stdout.write(tail[-4000:])
        sys.stdout.flush()

        if result.returncode == INCOMPLETE_EXIT_CODE:
            # Not success and not a crash: items are still outstanding and
            # a further pass resumes from the tape. Counted as a crash so
            # it cannot loop for ever.
            crashes += 1
            print(
                f"[supervisor] attempt {attempt} INCOMPLETE after "
                f"{elapsed / 60:.1f} min ({crashes}/{args.max_crashes})",
                flush=True,
            )
            if crashes >= args.max_crashes:
                return Outcome(
                    "incomplete",
                    f"items still unevaluated after {crashes} attempts",
                    ok=False,
                )
            time.sleep(BACKOFF_S)
            continue

        if result.returncode == 0:
            total = calls_spent(args.ledger)
            write_status(
                args.out_dir.parent,
                done(kind=KIND, phase=PHASE, calls_spent=total),
                phase=PHASE,
            )
            return Outcome(
                "success",
                f"{attempt} attempt(s), {total} P5 calls, {elapsed / 60:.1f} min last pass",
                ok=True,
            )

        refusal = classify(result.returncode, tail)
        if refusal is not None:
            return Outcome(refusal, f"exit {result.returncode}: {tail[-300:]}", ok=False)

        crashes += 1
        print(
            f"[supervisor] attempt {attempt} exited {result.returncode} "
            f"after {elapsed / 60:.1f} min ({crashes}/{args.max_crashes})",
            flush=True,
        )
        if crashes >= args.max_crashes:
            return Outcome(
                "crashes",
                f"{crashes} consecutive failures; last exit {result.returncode}: "
                f"{tail[-300:]}",
                ok=False,
            )
        time.sleep(BACKOFF_S)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Supervise a P5 evaluation.")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.json"))
    parser.add_argument("--out-dir", type=Path, default=Path("runs/p5"))
    parser.add_argument("--results-dir", type=Path, default=Path("data/results"))
    parser.add_argument("--ledger", type=Path, default=Path("runs/ledger.sqlite"))
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--item-concurrency", type=int, default=6)
    parser.add_argument("--top", type=int, default=3)
    parser.add_argument("--n", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20260917)
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--max-crashes", type=int, default=DEFAULT_MAX_CRASHES)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--per-step-sensitivity", action="store_true")
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    outcome = supervise(args)
    print(f"[supervisor] STOPPED reason={outcome.reason} · {outcome.detail}", flush=True)
    if not outcome.ok:
        write_status(
            args.out_dir.parent,
            failed(kind=KIND, phase=PHASE, error=f"{outcome.reason}: {outcome.detail}"),
            phase=PHASE,
        )
    return 0 if outcome.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
