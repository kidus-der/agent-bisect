#!/usr/bin/env python3
"""P0b step 1: measure NVIDIA NIM's real request rate limit by ramping to HTTP 429.

Protocol (pre-registered, do not change here — change the protocol first):
`docs/decisions/0004-p0-probe-protocol.md` §5.

Why raw httpx instead of `core.llm`: litellm normalises exceptions and
drops the HTTP response headers, and `LLMClient` deliberately *retries*
429s. Measuring the ceiling needs the opposite — one attempt per request,
the raw status code, and every `rate`/`limit`/`retry` response header.
Every attempt is still written to the same budget ledger (phase "P0",
purpose "rate_ramp") so P0's 4,000-call cap counts these too.

Resumable: after every window the whole state is rewritten to
`runs/p0/rate_limit.json`; re-running skips windows already recorded
(keyed by `(phase, model, target_rpm, index)`).

The API key is read via `core.config` and only ever placed in an
Authorization header; it is never logged, printed or stored.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from agent_bisect.core.budget import BudgetLedger, CallRecord
from agent_bisect.core.config import get_settings, redact

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = REPO_ROOT / "runs" / "p0" / "rate_limit.json"
LEDGER_PATH = REPO_ROOT / "runs" / "ledger.sqlite"

PHASE = "P0"
P0_CALL_CAP = 4000
RAMP_CALL_BUDGET = 1200
#: Protocol 0004 section 5.5 asks whether the limit is per model or account-wide,
#: but its step list never schedules the "each model alone" baseline that question
#: needs. This allowance pays for that one window, over and above the 1,200-call
#: ramp budget. The overage is deliberate, bounded and recorded in the state file.
ISOLATION_ALLOWANCE = 120
STATE_SCHEMA = 1

RAMP_RATES = (20, 40, 60, 90, 120, 160, 200)
WINDOW_S = 60.0
CONFIRM_WINDOWS = 2
REQUEST_TIMEOUT_S = 90.0
TINY_MAX_TOKENS = 1
TINY_PROMPT = "ok"
SAFETY_MARGIN = 0.10
MIN_SHORT_WINDOW_S = 15.0
SHORT_RAMP_FRACTIONS = (0.6, 0.8, 1.0)
COOLDOWN_POLL_S = 20.0
COOLDOWN_MAX_S = 300.0
RATE_LIMIT_STATUS = 429
HEADER_MARKERS = ("rate", "limit", "retry")

PRIMARY_MODEL = "openai/gpt-oss-20b"
SECOND_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
SHORT_RAMP_MODELS = (
    "deepseek-ai/deepseek-v4-flash-0731",
    "nvidia/nemotron-3-super-120b-a12b",
    "z-ai/glm-5.3-flash",
    "moonshotai/kimi-k3",
    "nvidia/nemotron-3-ultra-550b-a55b",
)


@dataclass(frozen=True)
class CallOutcome:
    """One single-attempt HTTP request. No retry: a 429 is the measurement."""

    status_code: int | None
    latency_ms: float
    retry_after: str | None = None
    rate_headers: dict[str, str] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class WindowResult:
    phase: str
    model: str
    target_rpm: int
    index: int
    duration_s: float
    sent: int
    ok: int
    rate_limited: int
    other_errors: int
    p50_ms: float
    p95_ms: float
    retry_after_values: list[str]
    rate_headers: dict[str, str]
    error_samples: list[str]

    @property
    def key(self) -> str:
        return f"{self.phase}|{self.model}|{self.target_rpm}|{self.index}"


def _rate_headers(headers: httpx.Headers) -> dict[str, str]:
    """Header names containing rate/limit/retry — never auth headers."""
    return {
        name: value
        for name, value in headers.items()
        if any(marker in name.lower() for marker in HEADER_MARKERS)
    }


async def fire_one(client: httpx.AsyncClient, model: str, delay_s: float) -> CallOutcome:
    """Wait `delay_s`, then make exactly one completion request. Never retries."""
    await asyncio.sleep(delay_s)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": TINY_PROMPT}],
        "max_tokens": TINY_MAX_TOKENS,
    }
    start = time.monotonic()
    try:
        response = await client.post("/chat/completions", json=payload)
    except Exception as exc:  # noqa: BLE001 - a transport failure is a datapoint, not a crash
        return CallOutcome(
            status_code=None,
            latency_ms=(time.monotonic() - start) * 1000,
            error=redact(f"{type(exc).__name__}: {exc}"),
        )
    latency_ms = (time.monotonic() - start) * 1000
    error = None if response.status_code < 400 else redact(response.text[:200])
    return CallOutcome(
        status_code=response.status_code,
        latency_ms=latency_ms,
        retry_after=response.headers.get("retry-after"),
        rate_headers=_rate_headers(response.headers),
        error=error,
    )


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(fraction * (len(ordered) - 1) + 0.5))
    return ordered[index]


def summarise(
    phase: str, model: str, target_rpm: int, index: int, duration_s: float,
    outcomes: list[CallOutcome],
) -> WindowResult:
    latencies = [o.latency_ms for o in outcomes]
    headers: dict[str, str] = {}
    for outcome in outcomes:
        headers.update(outcome.rate_headers)
    retry_after = sorted({o.retry_after for o in outcomes if o.retry_after})
    errors = sorted({o.error for o in outcomes if o.error})[:3]
    return WindowResult(
        phase=phase,
        model=model,
        target_rpm=target_rpm,
        index=index,
        duration_s=duration_s,
        sent=len(outcomes),
        ok=sum(1 for o in outcomes if o.status_code is not None and o.status_code < 400),
        rate_limited=sum(1 for o in outcomes if o.status_code == RATE_LIMIT_STATUS),
        other_errors=sum(1 for o in outcomes if _ledger_status(o) == "error"),
        p50_ms=statistics.median(latencies) if latencies else 0.0,
        p95_ms=_percentile(latencies, 0.95),
        retry_after_values=list(retry_after),
        rate_headers=headers,
        error_samples=[e for e in errors if e],
    )


def _ledger_status(outcome: CallOutcome) -> str:
    if outcome.status_code is None:
        return "error"
    if outcome.status_code == RATE_LIMIT_STATUS:
        return "rate_limited"
    return "ok" if outcome.status_code < 400 else "error"


def record_window(ledger: BudgetLedger, model: str, outcomes: list[CallOutcome]) -> None:
    now = time.time()
    for outcome in outcomes:
        ledger.record(
            CallRecord(
                ts=now,
                phase=PHASE,
                model=model,
                purpose="rate_ramp",
                status=_ledger_status(outcome),
                tokens_in=0,
                tokens_out=0,
                latency_ms=outcome.latency_ms,
            )
        )


def planned_calls(target_rpm: int, duration_s: float) -> int:
    return max(1, round(target_rpm * duration_s / 60.0))


async def run_window(
    client: httpx.AsyncClient, model: str, target_rpm: int, duration_s: float
) -> list[CallOutcome]:
    """Fire `target_rpm * duration/60` requests evenly spaced over the window."""
    count = planned_calls(target_rpm, duration_s)
    interval = duration_s / count
    tasks = [fire_one(client, model, i * interval) for i in range(count)]
    return list(await asyncio.gather(*tasks))


class Ramp:
    """Owns the resumable state file, the ledger and the ramp call budget."""

    def __init__(
        self, state_path: Path, ledger: BudgetLedger, *, allowance: int = RAMP_CALL_BUDGET
    ) -> None:
        self._state_path = state_path
        self._ledger = ledger
        self._allowance = allowance
        self._state = self._load()

    def _load(self) -> dict:
        if self._state_path.exists():
            return json.loads(self._state_path.read_text())
        return {
            "schema": STATE_SCHEMA,
            "protocol": "docs/decisions/0004-p0-probe-protocol.md",
            "windows": [],
            "measured_rpm": {},
            "account_wide": None,
            "notes": [],
        }

    def _save(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(self._state, indent=2, sort_keys=True))

    @property
    def state(self) -> dict:
        return self._state

    @property
    def calls_spent(self) -> int:
        return sum(w["sent"] for w in self._state["windows"])

    def budget_left(self) -> int:
        return self._allowance - self.calls_spent

    def find(self, phase: str, model: str, target_rpm: int, index: int) -> dict | None:
        key = f"{phase}|{model}|{target_rpm}|{index}"
        return next((w for w in self._state["windows"] if w["key"] == key), None)

    def note(self, text: str) -> None:
        self._state["notes"].append(text)
        self._save()

    def set_measured(self, model: str, rpm: int) -> None:
        self._state["measured_rpm"][model] = rpm
        self._save()

    def set_account_wide(self, value: bool, detail: str) -> None:
        self._state["account_wide"] = value
        self._state["account_wide_detail"] = detail
        self._save()

    async def window(
        self,
        client: httpx.AsyncClient,
        phase: str,
        model: str,
        target_rpm: int,
        duration_s: float,
        index: int = 0,
    ) -> dict:
        """Run one window, or return the recorded one if it already exists."""
        existing = self.find(phase, model, target_rpm, index)
        if existing is not None:
            print(f"  skip (done) {existing['key']}: "
                  f"{existing['ok']} ok / {existing['rate_limited']} 429")
            return existing
        # P0's own 4,000-call cap, on top of the ramp's 1,200.
        self._ledger.check_budget()
        need = planned_calls(target_rpm, duration_s)
        if need > self.budget_left():
            raise RampBudgetExhausted(
                f"window {phase}|{model}|{target_rpm} needs {need} calls, "
                f"{self.budget_left()} left of {self._allowance}"
            )
        outcomes = await run_window(client, model, target_rpm, duration_s)
        record_window(self._ledger, model, outcomes)
        result = summarise(phase, model, target_rpm, index, duration_s, outcomes)
        row = {**asdict(result), "key": result.key}
        self._state["windows"].append(row)
        self._save()
        print(
            f"  {result.key}: sent={result.sent} ok={result.ok} "
            f"429={result.rate_limited} other={result.other_errors} "
            f"p50={result.p50_ms:.0f}ms p95={result.p95_ms:.0f}ms"
        )
        return row


class RampBudgetExhausted(RuntimeError):
    """The ≤ 1,200-call ramp budget from the protocol would be exceeded."""


async def ramp_to_429(ramp: Ramp, client: httpx.AsyncClient, model: str) -> tuple[int, int | None]:
    """Full ramp on one model. Returns (last clean rpm, first rate that saw a 429)."""
    last_clean = 0
    for rate in RAMP_RATES:
        row = await ramp.window(client, "ramp", model, rate, WINDOW_S)
        if row["rate_limited"] > 0:
            return last_clean, rate
        last_clean = rate
    return last_clean, None


async def wait_for_cooldown(client: httpx.AsyncClient, model: str) -> float:
    """Poll with single tiny requests until a 429 no longer comes back."""
    waited = 0.0
    while waited < COOLDOWN_MAX_S:
        outcome = await fire_one(client, model, 0.0)
        if outcome.status_code != RATE_LIMIT_STATUS:
            return waited
        await asyncio.sleep(COOLDOWN_POLL_S)
        waited += COOLDOWN_POLL_S
    return waited


async def confirm_clean_rate(ramp: Ramp, client: httpx.AsyncClient, model: str, rate: int) -> bool:
    """Re-run the last clean rate for 2 minutes; True if it stays 429-free."""
    if rate <= 0:
        return False
    clean = True
    for index in range(1, CONFIRM_WINDOWS + 1):
        row = await ramp.window(client, "confirm", model, rate, WINDOW_S, index=index)
        clean = clean and row["rate_limited"] == 0
    return clean


async def account_wide_probe(
    ramp: Ramp, client: httpx.AsyncClient, measured_rpm: int
) -> tuple[bool, str]:
    """Two models at ~60% of the limit each, concurrently, for one window."""
    share = max(1, round(measured_rpm * 0.6))
    rows = await asyncio.gather(
        ramp.window(client, "pair", PRIMARY_MODEL, share, WINDOW_S),
        ramp.window(client, "pair", SECOND_MODEL, share, WINDOW_S),
    )
    limited = sum(row["rate_limited"] for row in rows)
    detail = (
        f"two models at {share} rpm each (~120% of the measured {measured_rpm} rpm "
        f"combined) for {WINDOW_S:.0f}s: {limited} HTTP 429 in total"
    )
    return limited > 0, detail


def short_window_duration(budget_left: int, models: int) -> float:
    """Fit 3 windows per model into what's left of the 1,200-call ramp budget."""
    per_model = max(1, budget_left // max(1, models))
    fractions = sum(SHORT_RAMP_FRACTIONS)
    return max(MIN_SHORT_WINDOW_S, min(WINDOW_S, per_model * 60.0 / (fractions * 200.0)))


async def short_ramp(
    ramp: Ramp, client: httpx.AsyncClient, model: str, measured_rpm: int, duration_s: float
) -> int | None:
    """3 windows around the found limit.

    Returns the highest rate this model sustained with zero 429s, or **None**
    when even the lowest window was throttled: that is "ceiling below this
    rate, not bracketed", which is not the same as a measured 0 and must not
    be recorded as one.
    """
    measured: int | None = None
    for fraction in SHORT_RAMP_FRACTIONS:
        rate = max(1, round(measured_rpm * fraction))
        row = await ramp.window(client, "short", model, rate, duration_s)
        if row["rate_limited"] > 0:
            return measured
        measured = rate
    return measured


def limiter_rpm(measured_rpm: int) -> int:
    return max(1, int(measured_rpm * (1 - SAFETY_MARGIN)))


async def _run_primary(ramp: Ramp, client: httpx.AsyncClient) -> int:
    """Ramp the primary model, cool down, confirm. Returns its measured rpm."""
    print(f"ramp: {PRIMARY_MODEL}")
    last_clean, first_429 = await ramp_to_429(ramp, client, PRIMARY_MODEL)
    if first_429 is None:
        ramp.note(f"no 429 up to {RAMP_RATES[-1]} rpm on {PRIMARY_MODEL}; treating "
                  f"{RAMP_RATES[-1]} as the measured value")
        measured = RAMP_RATES[-1]
    else:
        waited = await wait_for_cooldown(client, PRIMARY_MODEL)
        ramp.note(f"first 429 at {first_429} rpm on {PRIMARY_MODEL}; "
                  f"429s stopped after ~{waited:.0f}s")
        clean = await confirm_clean_rate(ramp, client, PRIMARY_MODEL, last_clean)
        ramp.note(f"confirmation of {last_clean} rpm for {CONFIRM_WINDOWS} minutes: "
                  f"{'clean' if clean else 'saw 429s'}")
        measured = last_clean
    ramp.set_measured(PRIMARY_MODEL, measured)
    return measured


async def _run_others(ramp: Ramp, client: httpx.AsyncClient, measured: int) -> None:
    """Account-wide probe, then a short ramp per remaining candidate."""
    account_wide, detail = await account_wide_probe(ramp, client, measured)
    ramp.set_account_wide(account_wide, detail)
    print(f"account-wide: {account_wide} — {detail}")
    # Deliberately NOT ramp.set_measured(SECOND_MODEL, measured): the pair
    # window measures the second model *under contention*, which is not its
    # own ceiling. Use --isolate to measure it alone.

    duration = short_window_duration(ramp.budget_left(), len(SHORT_RAMP_MODELS))
    print(f"short ramps: {duration:.0f}s windows, {ramp.budget_left()} calls left")
    for model in SHORT_RAMP_MODELS:
        try:
            rpm = await short_ramp(ramp, client, model, measured, duration)
            if rpm is None:
                ramp.note(f"{model}: 429 at the lowest window tried; ceiling below it and "
                          f"not bracketed -- deliberately left unmeasured")
            else:
                ramp.set_measured(model, rpm)
        except RampBudgetExhausted as exc:
            ramp.note(f"short ramp for {model} skipped: {exc}")
            print(f"  skip {model}: {exc}")


async def isolate(
    ramp: Ramp, client: httpx.AsyncClient, model: str, rate: int, duration_s: float
) -> dict:
    """One model alone at `rate`, to settle protocol §5.5.

    The pair window only shows that *someone* was throttled. Deciding
    per-model vs account-wide needs each model's behaviour alone at the same
    rate: 429s alone mean that model's own ceiling is lower; clean alone
    means the combined rate caused them.
    """
    row = await ramp.window(client, "isolate", model, rate, duration_s)
    verdict = "its own ceiling is below this rate" if row["rate_limited"] else "clean alone"
    ramp.note(
        f"isolation window: {model} alone at {rate} rpm for {duration_s:.0f}s -> "
        f"{row['rate_limited']} HTTP 429 of {row['sent']} ({verdict})"
    )
    return row


async def run(only: str | None) -> Ramp:
    settings = get_settings()
    if not settings.has_nvidia_key:
        raise SystemExit("NVIDIA_API_KEY not set; cannot measure the rate limit.")
    assert settings.nvidia_api_key is not None

    ledger = BudgetLedger(LEDGER_PATH, max_calls=P0_CALL_CAP)
    ramp = Ramp(STATE_PATH, ledger)
    headers = {"Authorization": f"Bearer {settings.nvidia_api_key.get_secret_value()}"}
    async with httpx.AsyncClient(
        base_url=settings.nvidia_base_url, headers=headers, timeout=REQUEST_TIMEOUT_S
    ) as client:
        measured = ramp.state["measured_rpm"].get(PRIMARY_MODEL)
        if measured is None:
            measured = await _run_primary(ramp, client)
        print(f"measured for {PRIMARY_MODEL}: {measured} rpm "
              f"(limiter -> {limiter_rpm(measured)})")
        if only != "primary":
            await _run_others(ramp, client, measured)
    return ramp


async def run_isolation(model: str, rate: int, duration_s: float) -> Ramp:
    settings = get_settings()
    if not settings.has_nvidia_key:
        raise SystemExit("NVIDIA_API_KEY not set; cannot measure the rate limit.")
    assert settings.nvidia_api_key is not None
    ledger = BudgetLedger(LEDGER_PATH, max_calls=P0_CALL_CAP)
    ramp = Ramp(STATE_PATH, ledger, allowance=RAMP_CALL_BUDGET + ISOLATION_ALLOWANCE)
    headers = {"Authorization": f"Bearer {settings.nvidia_api_key.get_secret_value()}"}
    async with httpx.AsyncClient(
        base_url=settings.nvidia_base_url, headers=headers, timeout=REQUEST_TIMEOUT_S
    ) as client:
        await isolate(ramp, client, model, rate, duration_s)
    return ramp


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only", choices=("primary", "all"), default="all",
        help="'primary' stops after the first model's full ramp.",
    )
    parser.add_argument("--isolate", default=None,
                        help="Measure one model ALONE at --rate, to settle per-model "
                             "vs account-wide (protocol 0004 section 5.5).")
    parser.add_argument("--rate", type=int, default=120)
    parser.add_argument("--window", type=float, default=WINDOW_S)
    args = parser.parse_args()
    if args.isolate:
        ramp = asyncio.run(run_isolation(args.isolate, args.rate, args.window))
        print(f"\nwrote {STATE_PATH}")
        for note in ramp.state["notes"][-1:]:
            print(f"  {note}")
        return
    ramp = asyncio.run(run(None if args.only == "all" else args.only))
    print(f"\nwrote {STATE_PATH} ({ramp.calls_spent} ramp calls spent, "
          f"{ramp.budget_left()} left of {RAMP_CALL_BUDGET})")
    for model, rpm in sorted(ramp.state["measured_rpm"].items()):
        print(f"  {model}: measured {rpm} rpm -> limiter {limiter_rpm(rpm)} rpm")


if __name__ == "__main__":
    main()
