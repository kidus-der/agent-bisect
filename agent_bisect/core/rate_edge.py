"""Finding each model's real rate ceiling, without going over it.

P0 bracketed the limits rather than locating them: the agent model was
clean at 120 rpm and returned 429s at 160, the user simulator returned
them below 120 (`docs/decisions/0004-p0-probe-protocol.md` §5). The
limiter was then set to the conservative end of each bracket — 108 and 60
— which is correct and leaves most of the account's capacity unused.

This walks each model's rate up while the provider is quiet and backs it
down the moment it is not: **additive increase** of a few rpm after
several consecutive clean windows, **multiplicative decrease** on any
window carrying a burst of 429s, bounded below by the configured value
and above by a ceiling derived from what P0 measured. A 429 is a signal,
never a failure — the retry policy in `core.llm` is untouched and still
absorbs them; this only decides how fast to offer work.

**It observes the ledger, not the calls.** Every call already records its
model, its outcome (`ok`, `rate_limited`, `retrying`, `exhausted`,
`error`) and its latency, so the controller needs no hook into the
request path and cannot itself become a source of failure. Every window
is appended to `runs/limits/<model>.jsonl`, and the steady rate each
model settles at is written back to `config/limits.toml` as
`[limiter.measured_rpm_edge]`, so later phases inherit what was learned
here instead of re-discovering it.

The same measurements answer a second question: how many calls must be in
flight for the *limiter* to be what binds rather than latency. At `r`
requests per minute and a median call taking `L` seconds, that is
`r x L / 60` by Little's law, plus a quarter for slack.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.llm import TokenBucketLimiter

#: Ledger statuses that mean the provider refused for rate.
RATE_LIMITED = "rate_limited"
#: Ledger statuses that mean a call completed.
COMPLETED = "ok"

DEFAULT_LOG_DIR = Path("runs/limits")
#: The agent makes roughly this many calls for each user-simulator call,
#: so the user simulator binds when its rate is below the agent's over
#: this. Measured on the P1 recordings: agent and evaluator turns
#: outnumber user turns about three to one.
AGENT_TO_USER_CALLS = 3.0


@dataclass(frozen=True)
class EdgePolicy:
    """How boldly to climb, and how sharply to retreat."""

    #: Consecutive clean windows before the rate goes up.
    clean_windows_before_increase: int = 3
    #: How much it goes up by.
    increase_rpm: float = 4.0
    #: What it is multiplied by on a storm.
    decrease_factor: float = 0.8
    #: 429s in one window that count as a storm rather than noise.
    storm_429s: int = 2
    window_seconds: float = 60.0
    #: Headroom over Little's law, so the bucket stays the binding thing.
    thread_headroom: float = 1.25
    max_threads: int = 48
    min_threads: int = 4
    #: A window completing less than this share of what it sent is
    #: congested, whatever the status codes say.
    healthy_completion: float = 0.5
    #: How far p50 latency may drift above the best seen before the
    #: concurrency is treated as the cause.
    latency_inflation: float = 2.0


@dataclass(frozen=True)
class WindowReport:
    """One model's minute, as the ledger recorded it."""

    ts: float
    model: str
    target_rpm: float
    sent: int
    ok: int
    http_429: int
    other_errors: int
    p50_latency_ms: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "model": self.model,
            "target_rpm": self.target_rpm,
            "sent": self.sent,
            "ok": self.ok,
            "http_429": self.http_429,
            "other_errors": self.other_errors,
            "p50_latency_ms": round(self.p50_latency_ms, 1),
        }


class AdaptiveLimiter:
    """A token bucket whose rate can be changed while it is in use.

    `core.llm.TokenBucketLimiter` is built once at a fixed rate, which is
    right for it; retuning is this wrapper's business. Callers hold this
    object for the life of the run and never see it swap underneath them.
    """

    def __init__(self, requests_per_minute: float) -> None:
        self._lock = threading.Lock()
        self._bucket = TokenBucketLimiter(requests_per_minute)

    @property
    def requests_per_minute(self) -> float:
        with self._lock:
            return self._bucket.requests_per_minute

    def retune(self, requests_per_minute: float) -> None:
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be positive")
        with self._lock:
            if requests_per_minute == self._bucket.requests_per_minute:
                return
            self._bucket = TokenBucketLimiter(requests_per_minute)

    def _current(self) -> TokenBucketLimiter:
        with self._lock:
            return self._bucket

    def acquire_sync(self) -> None:
        self._current().acquire_sync()

    async def acquire(self) -> None:
        await self._current().acquire()


class RateEdge:
    """Per-model AIMD over what the ledger says actually happened."""

    def __init__(
        self,
        *,
        ledger: BudgetLedger,
        floors: Mapping[str, float],
        ceilings: Mapping[str, float],
        log_dir: Path = DEFAULT_LOG_DIR,
        policy: EdgePolicy | None = None,
    ) -> None:
        self._ledger = ledger
        self._floors = dict(floors)
        self._ceilings = dict(ceilings)
        self._log_dir = log_dir
        self._policy = policy or EdgePolicy()
        self._rates: dict[str, float] = dict(floors)
        self._clean: dict[str, int] = dict.fromkeys(floors, 0)
        self._limiters: dict[str, AdaptiveLimiter] = {}
        self._latency: dict[str, float] = {}
        #: The quickest this model has been seen to answer. Congestion is
        #: measured against it, because the inflated figure is the symptom.
        self._best_latency: dict[str, float] = {}
        self._congested = False
        self._last_step = time.time()
        self._lock = threading.Lock()
        self._stopping = threading.Event()

    # -- what callers use ---------------------------------------------------

    def limiter_for(self, model: str) -> AdaptiveLimiter:
        """The bucket this model's calls pass through, for the whole run."""
        with self._lock:
            limiter = self._limiters.get(model)
            if limiter is None:
                limiter = AdaptiveLimiter(self._rate_of(model))
                self._limiters[model] = limiter
            return limiter

    def edges(self) -> dict[str, float]:
        with self._lock:
            return dict(self._rates)

    def recommended_threads(self) -> int:
        """How many calls must be in flight for the limiter to be what binds.

        Little's law over the busiest model, with headroom — but computed
        from the **best** latency that model has shown, never the current
        one. Using the current figure is a positive feedback loop and it
        cost this collection most of its budget: offering more work
        inflates latency, inflated latency asks for more threads, and the
        provider answers slower still. Measured, the p50 went from 9.5 s
        to 36 s while the controller kept raising the thread count, and
        retries outnumbered successes 43,378 to 25,377.

        A window that completes less than half of what it sent is
        congested whatever its status codes say, and halves the answer.
        """
        model = max(
            self._best_latency, key=lambda name: self._best_latency.get(name, 0.0), default=None
        )
        if model is None:
            return self._policy.min_threads
        seconds = self._best_latency[model] / 1000.0
        wanted = self._rate_of(model) * seconds / 60.0 * self._policy.thread_headroom
        if self._congested:
            wanted /= 2
        return int(min(self._policy.max_threads, max(self._policy.min_threads, round(wanted))))

    def binding_model(self) -> str | None:
        """The model whose ceiling is holding the whole collection back.

        The agent makes about three calls for every user-simulator call,
        so the user simulator binds once its rate falls below a third of
        the agent's — a fact worth stating rather than leaving someone to
        infer it from a rate that will not climb.
        """
        with self._lock:
            rates = dict(self._rates)
        if len(rates) < 2:
            return None
        fastest = max(rates.values())
        for model, rate in sorted(rates.items()):
            if rate < fastest / AGENT_TO_USER_CALLS:
                return model
        return None

    # -- the control loop ---------------------------------------------------

    def step(self, now: float | None = None) -> list[WindowReport]:
        """Read one window off the ledger and act on it."""
        moment = now if now is not None else time.time()
        window = max(self._policy.window_seconds, moment - self._last_step)
        reports = [
            self._window_for(model, moment, window) for model in sorted(self._floors)
        ]
        live = [report for report in reports if report.sent > 0]
        self._congested = bool(live) and any(
            report.ok / report.sent < self._policy.healthy_completion
            or (
                self._best_latency.get(report.model)
                and report.p50_latency_ms
                > self._best_latency[report.model] * self._policy.latency_inflation
            )
            for report in live
        )
        for report in reports:
            self._react(report)
            self._log(report)
        self._last_step = moment
        return reports

    def start(self) -> threading.Thread:
        """Run `step` every window in the background until `stop`."""

        def loop() -> None:
            while not self._stopping.wait(self._policy.window_seconds):
                try:
                    self.step()
                except Exception:  # noqa: BLE001 - pacing must never kill a collection
                    continue

        thread = threading.Thread(target=loop, name="rate-edge", daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self._stopping.set()

    # -- internals ----------------------------------------------------------

    def _rate_of(self, model: str) -> float:
        return self._rates.get(model, self._floors.get(model, 60.0))

    def _window_for(self, model: str, moment: float, window: float) -> WindowReport:
        rows = self._rows(model, moment - window)
        latencies = sorted(
            latency for status, latency in rows if status == COMPLETED and latency
        )
        if latencies:
            p50 = latencies[len(latencies) // 2]
            self._latency[model] = p50
            best = self._best_latency.get(model)
            self._best_latency[model] = p50 if best is None else min(best, p50)
        return WindowReport(
            ts=moment,
            model=model,
            target_rpm=self._rate_of(model),
            sent=len(rows),
            ok=sum(1 for status, _l in rows if status == COMPLETED),
            http_429=sum(1 for status, _l in rows if status == RATE_LIMITED),
            other_errors=sum(
                1 for status, _l in rows if status in {"error", "exhausted"}
            ),
            p50_latency_ms=self._latency.get(model, 0.0),
        )

    def _rows(self, model: str, since: float) -> list[tuple[str, float]]:
        try:
            connection = sqlite3.connect(
                f"file:{self._ledger_path()}?mode=ro", uri=True, timeout=5.0
            )
        except sqlite3.Error:  # pragma: no cover - a locked ledger is not fatal
            return []
        try:
            return [
                (str(status), float(latency or 0.0))
                for status, latency in connection.execute(
                    "SELECT status, latency_ms FROM calls WHERE model = ? AND ts > ?",
                    (model, since),
                )
            ]
        except sqlite3.Error:  # pragma: no cover
            return []
        finally:
            connection.close()

    def _ledger_path(self) -> Path:
        return self._ledger._db_path  # noqa: SLF001 - read-only, same process

    def _react(self, report: WindowReport) -> None:
        model = report.model
        with self._lock:
            if report.http_429 >= self._policy.storm_429s:
                self._clean[model] = 0
                self._rates[model] = max(
                    self._floors[model], self._rates[model] * self._policy.decrease_factor
                )
            elif report.sent > 0:
                self._clean[model] = self._clean.get(model, 0) + 1
                if self._clean[model] >= self._policy.clean_windows_before_increase:
                    self._clean[model] = 0
                    self._rates[model] = min(
                        self._ceilings.get(model, self._rates[model]),
                        self._rates[model] + self._policy.increase_rpm,
                    )
            rate = self._rates[model]
            limiter = self._limiters.get(model)
        if limiter is not None:
            limiter.retune(rate)

    def _log(self, report: WindowReport) -> None:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        path = self._log_dir / f"{report.model.replace('/', '_')}.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(report.as_dict(), sort_keys=True) + "\n")


_EDGE_TABLE = "[limiter.measured_rpm_edge]"


def write_back_edges(path: Path, edges: Mapping[str, float]) -> Path:
    """Record the discovered rates in `config/limits.toml`.

    Written as its own table rather than over `per_model`, so what P0
    *measured* and what this run *discovered* stay distinguishable — and
    so a later phase inherits the edge instead of paying to find it again.
    """
    body = "\n".join(f'"{model}" = {rate}' for model, rate in sorted(edges.items()))
    block = f"{_EDGE_TABLE}\n# Discovered by core.rate_edge during collection.\n{body}\n"
    text = path.read_text() if path.exists() else ""
    existing = re.search(
        rf"^{re.escape(_EDGE_TABLE)}\n(?:(?!^\[).*\n)*", text, flags=re.MULTILINE
    )
    if existing:
        text = text[: existing.start()] + block + text[existing.end() :]
    else:
        text = text.rstrip("\n") + "\n\n" + block
    path.write_text(text)
    return path
