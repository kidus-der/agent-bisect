#!/usr/bin/env python
"""Hold the P5 test split, burst-probe the provider, relaunch when it recovers.

    uv run python scripts/p5_watch.py [--cutoff 2026-09-21T06:00:00-06:00]

Decision 0023. The evaluation stopped because the provider's limit is
token-based, not request-based (`docs/findings/token-rate-limit.md`): at
the moment 8 concurrent ~2,500-token requests were succeeding 1/8, a
single trivial request still came back in ~2 s. A solo health probe would
therefore have reported "healthy" through the whole degradation, so the
probe here is a **burst of 8 concurrent realistic requests**, judged on
how many come back inside 60 seconds — the same shape as the load the
relaunch will apply, so a pass means "this concurrency works", not "some
smaller concurrency works".

Each probe request is a single attempt (`max_elapsed_s=0`): a retry would
turn the measurement into "the provider eventually answered", which is
not the question. The burst deliberately uses its own limiter rather than
the shared one — spacing the burst out would measure the limiter instead
of the provider — and it only ever runs while the evaluation is stopped.

Three consecutive probes at >= 6/8 within 60 s relaunch the supervisor
with `--resume`; the cutoff stops the watch whatever the state. Every
probe is appended to `runs/p5/probes.jsonl` and mirrored into
`runs/p5/status.json` so the hourly check sees real numbers.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.config import get_settings
from agent_bisect.core.llm import (
    LiteLLMTransport,
    LLMClient,
    LLMClientConfig,
    LLMRequest,
    TokenBucketLimiter,
)
from agent_bisect.core.models import load_chosen_models

PHASE = "P5"
RUNS_DIR = Path("runs")
OUT_DIR = RUNS_DIR / "p5"
PROBE_LOG = OUT_DIR / "probes.jsonl"
STATUS = OUT_DIR / "status.json"
STOP_FILE = OUT_DIR / "STOP"

#: The burst, and the bar it has to clear, from decision 0023 as amended
#: at 19:45 MDT: 8 concurrent rather than 10, passing at 6, relaunching at
#: 8 in flight — the burst now matches the concurrency it authorises, so
#: the probe measures the load the evaluation will actually apply.
BURST = 8
PASS_AT = 6
BURST_DEADLINE_S = 60.0
CONSECUTIVE_PASSES = 3
PROBE_INTERVAL_S = 15 * 60

#: ~2,500 input tokens: a τ² agent turn's size, which is the payload the
#: token-based limit actually rejects. A trivial prompt is not a probe.
PROBE_INPUT_WORDS = 1900
PROBE_MAX_TOKENS = 300
#: Far above the burst so the probe measures the provider, not our bucket.
PROBE_RPM = 600.0
#: Probe traffic is P5 spend and is ledgered as such, under its own purpose.
PROBE_PURPOSE = "probe"

RELAUNCH_CONCURRENCY = 8
#: How often the relaunched supervisor is checked on. Long, because the
#: answer only changes when it exits.
SUPERVISOR_POLL_S = 60.0

#: A relaunched run is watched for *productive* calls, not for liveness.
#: The 02:48Z relaunch passed three clean bursts and then spent 17,525
#: calls in three hours for 136 answers — 98% retries — because a run
#: that is 429-ing is indistinguishable from a busy one unless the
#: ledger is read. Below this rate over `STALL_WINDOW_S`, and past the
#: grace period that lets the first judge calls land, the run is buying
#: nothing and is stopped.
MIN_OK_PER_MIN = 2.0
STALL_WINDOW_S = 900.0
STALL_GRACE_S = 1200.0
MAX_CALLS = 120_000


@dataclass(frozen=True, slots=True)
class BurstResult:
    """One probe: how many of `BURST` answered, and how fast."""

    at: str
    ok: int
    failed: int
    seconds: float
    latencies: tuple[float, ...]
    errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return self.ok >= PASS_AT and self.seconds <= BURST_DEADLINE_S

    def as_dict(self) -> dict[str, object]:
        return {
            "at": self.at,
            "ok": self.ok,
            "failed": self.failed,
            "of": BURST,
            "seconds": round(self.seconds, 1),
            "latencies": [round(value, 1) for value in self.latencies],
            "errors": list(self.errors),
            "passed": self.passed,
        }


def probe_prompt() -> tuple[dict[str, str], ...]:
    """A deterministic filler payload of roughly one agent turn's size."""
    filler = " ".join(f"line{index}" for index in range(PROBE_INPUT_WORDS))
    return (
        {"role": "system", "content": "You are a capacity probe. Answer with one word."},
        {"role": "user", "content": f"{filler}\n\nReply with the word OK."},
    )


def _client(ledger: BudgetLedger) -> tuple[LLMClient, str]:
    settings = get_settings()
    key = settings.nvidia_api_key
    if key is None:
        raise SystemExit("NVIDIA_API_KEY is not set; the watcher cannot probe.")
    client = LLMClient(
        LiteLLMTransport(),
        ledger,
        api_base=settings.nvidia_base_url,
        api_key=key.get_secret_value(),
        # One attempt per request: a retried probe measures patience.
        config=LLMClientConfig(max_elapsed_s=0.0),
        limiter=TokenBucketLimiter(PROBE_RPM),
    )
    return client, load_chosen_models().agent


async def _one(client: LLMClient, request: LLMRequest) -> tuple[float, str | None]:
    started = time.monotonic()
    try:
        await client.complete(request, phase=PHASE)
    except Exception as exc:  # noqa: BLE001 - every failure is a datum here
        return time.monotonic() - started, f"{type(exc).__name__}: {exc}"[:160]
    return time.monotonic() - started, None


async def burst(ledger: BudgetLedger) -> BurstResult:
    """Fire `BURST` realistic requests at once and report what came back."""
    client, model = _client(ledger)
    request = LLMRequest(
        model=model,
        messages=probe_prompt(),
        max_tokens=PROBE_MAX_TOKENS,
        purpose=PROBE_PURPOSE,
    )
    at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    results = await asyncio.gather(*[_one(client, request) for _ in range(BURST)])
    elapsed = time.monotonic() - started
    latencies = tuple(seconds for seconds, error in results if error is None)
    errors = tuple(sorted({error for _, error in results if error is not None}))
    return BurstResult(
        at=at,
        ok=len(latencies),
        failed=BURST - len(latencies),
        seconds=elapsed,
        latencies=latencies,
        errors=errors,
    )


def record(result: BurstResult, consecutive: int, spent: int, cutoff: datetime) -> None:
    """Append the probe and mirror it into the paused status file.

    `state: "paused"` is not one of the four states `server.schemas_live`
    accepts; a status it cannot parse is skipped by the real repository
    rather than breaking the Live page, and the team lead asked for the
    paused state by name so the hold is unmistakable in the file.
    """
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with PROBE_LOG.open("a") as handle:
        handle.write(json.dumps(result.as_dict(), sort_keys=True) + "\n")
    payload = {
        "kind": "eval",
        "phase": PHASE,
        "state": "paused",
        "progress": 1 / 12,
        "label": "P5 test split held (decision 0023)",
        "items_done": 1,
        "items_total": 12,
        "calls_spent": spent,
        "started_at": "2026-09-20T21:37:56.177143+00:00",
        "finished_at": None,
        "eta_seconds": None,
        "last_checkpoint_at": result.at,
        "error": None,
        "reason": (
            "provider capacity collapsed to ~1 concurrent request on the agent "
            "model from 18:00 MDT on 2026-09-20; see docs/decisions/0023-p5-cutoff.md"
        ),
        "last_probe": result.as_dict(),
        "consecutive_passes": consecutive,
        "passes_needed": CONSECUTIVE_PASSES,
        "cutoff": cutoff.isoformat(),
    }
    temporary = STATUS.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(temporary, STATUS)


def relaunch(log_path: Path) -> subprocess.Popen[bytes]:
    """Start the supervisor on the test split, detached."""
    command = [
        "uv", "run", "python", "scripts/p5_supervisor.py",
        "--split", "test", "--resume",
        "--concurrency", str(RELAUNCH_CONCURRENCY),
        "--item-concurrency", "4",
        "--methods", "bisect,judge_all_at_once,judge_step_by_step",
        "--max-calls", str(MAX_CALLS),
    ]
    handle = log_path.open("a")
    return subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        command, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True
    )


def productive_rate(ledger_path: Path, window_s: float = STALL_WINDOW_S) -> float:
    """Answered P5 calls per minute over the last `window_s`.

    Read straight from the ledger because that is the only place a
    retry is distinguishable from an answer. `ts` is a UNIX float, and
    a row's status is updated in place when the call finishes.
    """
    since = time.time() - window_s
    with sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True) as connection:
        answered = connection.execute(
            "select count(*) from calls where phase = ? and status = 'ok' and ts >= ?",
            (PHASE, since),
        ).fetchone()[0]
    return float(answered) / (window_s / 60.0)


def stop_run(out_dir: Path = OUT_DIR) -> None:
    """Stop a running evaluation the way a human would, without orphans.

    The stop file makes the supervisor refuse to start another attempt;
    terminating the `bisect eval` process itself is what ends the
    attempt already in flight. Killing the supervisor instead would
    leave its child running against the same tape.
    """
    (out_dir / STOP_FILE.name).touch()
    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["pkill", "-TERM", "-f", "bisect eval --split test"], check=False
    )


def wait_for(
    process: subprocess.Popen[bytes], cutoff: datetime, ledger_path: Path
) -> int | None:
    """Wait out the supervisor, stopping it if it stops buying anything.

    `None` means the cutoff came first. A supervisor still *working* at
    the cutoff is left running: it is spending on items that resume from
    the tape, and killing it mid-fork would throw that away. A supervisor
    that is only retrying is stopped whenever that becomes clear.
    """
    started = time.monotonic()
    while datetime.now(cutoff.tzinfo) < cutoff:
        code = process.poll()
        if code is not None:
            STOP_FILE.unlink(missing_ok=True)
            return code
        if time.monotonic() - started >= STALL_GRACE_S:
            rate = productive_rate(ledger_path)
            if rate < MIN_OK_PER_MIN:
                print(
                    f"[watch] STALLED · {rate:.2f} answered calls/min over the last "
                    f"{STALL_WINDOW_S / 60:.0f} min; stopping the run",
                    flush=True,
                )
                stop_run()
        time.sleep(SUPERVISOR_POLL_S)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hold, probe, relaunch (decision 0023).")
    parser.add_argument("--cutoff", default="2026-09-21T06:00:00-06:00")
    parser.add_argument("--ledger", type=Path, default=RUNS_DIR / "ledger.sqlite")
    parser.add_argument("--log", type=Path, default=OUT_DIR / "supervisor-test.log")
    parser.add_argument("--interval", type=float, default=PROBE_INTERVAL_S)
    args = parser.parse_args(argv)

    cutoff = datetime.fromisoformat(args.cutoff)
    ledger = BudgetLedger(args.ledger)
    consecutive = 0
    while datetime.now(cutoff.tzinfo) < cutoff:
        if STOP_FILE.exists():
            print(f"[watch] STOPPED reason=stop_file · {STOP_FILE} exists", flush=True)
            return 0
        result = asyncio.run(burst(ledger))
        consecutive = consecutive + 1 if result.passed else 0
        spent = ledger.totals_per_phase().get(PHASE, 0)
        record(result, consecutive, spent, cutoff)
        print(
            f"[watch] {result.at} ok={result.ok}/{BURST} in {result.seconds:.1f}s "
            f"· passes {consecutive}/{CONSECUTIVE_PASSES} · {spent} P5 calls",
            flush=True,
        )
        if consecutive >= CONSECUTIVE_PASSES:
            process = relaunch(args.log)
            print(
                f"[watch] RELAUNCHED supervisor pid={process.pid} → {args.log}", flush=True
            )
            code = wait_for(process, cutoff, args.ledger)
            if code is None:
                print("[watch] STOPPED reason=cutoff · supervisor still running", flush=True)
                return 2
            if code == 0:
                print("[watch] STOPPED reason=success · the test split finished", flush=True)
                return 0
            # It came back up and fell over again. Go back to probing
            # rather than leaving the overnight window unused.
            consecutive = 0
            print(f"[watch] supervisor exited {code}; resuming probes", flush=True)
        time.sleep(args.interval)

    print(f"[watch] STOPPED reason=cutoff · {cutoff.isoformat()} reached", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(main())
