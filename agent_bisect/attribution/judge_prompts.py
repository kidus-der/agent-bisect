"""Rendering a failed trajectory for the judge, and the two Who&When prompts.

Provenance
----------
The two protocols are those of **Who&When** — Zhang et al., *"Which Agent
Causes Task Failures and When? On Automated Failure Attribution of LLM
Multi-Agent Systems"*, ICML 2025 (arXiv:2505.00212) — as described in the
paper and its released prompts:

- **All-at-Once**: the judge is shown the task and the *entire* failure log
  in one prompt and asked, in a single pass, which participant is
  responsible, at which step the decisive error occurred, and why.
- **Step-by-Step**: the judge walks the log forward one step at a time,
  is asked at each step whether the decisive error is *this* step, and
  stops at the first "yes".

Faithful to the published protocol: the single-pass vs incremental shape;
the "decisive error" framing (the step at which something went wrong that
directly led to the failure, not merely a step that looks suspicious); the
judge seeing the task description and the log and nothing else; naming both
a responsible participant and a step index with a short reason; the
step-by-step judge never seeing steps it has not reached.

**Adaptations, marked as such** (the paper's subjects are multi-agent LLM
teams; ours is a tau2 customer-service simulation):

1. *Participants.* Who&When asks "which agent"; tau2 has three fixed
   parties (`agent`, `user`, `tool`), so the question becomes "which
   party's step", and agent-level accuracy is not reported at all —
   `docs/brief/summary.md` §2 says Bisect names the causal **step**.
2. *Output format.* The paper parses a free-text answer. We require one
   strict JSON object and validate it against a schema, with one repair
   retry, because a silent parse failure would quietly drop items
   (`attribution/judge.py` counts a parse failure as a wrong answer).
3. *Ranking.* The paper asks for one step. We additionally ask for a
   ranked list of up to `RANKING_LIMIT` suspects, because P5 reports
   recall@m for m = 1..10 and because Bisect's shortlist (m = 3) must come
   from the same call, so every method shares one judge output per item.
   The schema requires `ranking[0].step == decisive_step`, so the
   protocol's own answer is exactly the baseline's answer — the extra ask
   cannot silently improve or degrade the top-1 result it is compared on.
4. *The policy document.* tau2 gives the agent a domain policy; the judge
   is given the same text, because a user of the tool would have it and
   because most airline/retail failures are policy violations.

Truncation
----------
A trajectory can exceed any context window. The policy is fixed here and
documented because it is a measurement decision, not a detail:

- every step is rendered, always — a step is **never** dropped, because a
  dropped step is a step the judge cannot possibly name, which would
  silently cap recall;
- only *payloads* are shortened, keeping the head and the tail (a tool
  result's opening fields and its closing ones) with an explicit marker
  saying how many characters were removed;
- if the whole rendering still exceeds `max_total_chars`, the per-step
  budget is lowered **uniformly** for every step (binary search for the
  largest budget that fits) rather than spending the budget on whichever
  steps come first;
- the per-step budget never goes below `MIN_CHARS_PER_STEP`. If even that
  does not fit, the rendering is allowed to exceed the total budget: going
  over is visible and recoverable, dropping steps is neither.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from agent_bisect.attribution.judge_view import JudgeInput, JudgeStepView
from agent_bisect.core.config import redact
from agent_bisect.core.store import canonical_json_bytes

#: Most suspects the judge is asked to rank. P5 reports recall@m for
#: m = 1..10, so the ranking has to be at least that long.
RANKING_LIMIT = 10

#: Never shrink a step below this many characters of payload. Below it a
#: step stops being recognisable, and a judge that cannot tell two steps
#: apart is being measured on the renderer rather than on itself.
MIN_CHARS_PER_STEP = 80

ELISION_TEMPLATE = "…[{elided} characters elided]…"

_INDENT = "  "


@dataclass(frozen=True, slots=True)
class TruncationPolicy:
    """How much of each payload the judge sees. Identical for every step."""

    max_chars_per_step: int = 1_200
    head_fraction: float = 0.6
    max_total_chars: int = 60_000

    def __post_init__(self) -> None:
        # `MIN_CHARS_PER_STEP` bounds the *automatic* shrinking in
        # `render_trajectory`, not what a caller may ask for deliberately.
        if self.max_chars_per_step <= 0:
            raise ValueError(
                f"max_chars_per_step must be positive, got {self.max_chars_per_step}"
            )
        if not 0.0 < self.head_fraction < 1.0:
            raise ValueError(f"head_fraction must be in (0, 1), got {self.head_fraction}")
        if self.max_total_chars <= 0:
            raise ValueError(f"max_total_chars must be positive, got {self.max_total_chars}")

    def with_step_budget(self, chars: int) -> TruncationPolicy:
        """A copy at a different per-step budget; never mutates the original."""
        return TruncationPolicy(
            max_chars_per_step=max(MIN_CHARS_PER_STEP, chars),
            head_fraction=self.head_fraction,
            max_total_chars=self.max_total_chars,
        )


def truncate(text: str, policy: TruncationPolicy) -> str:
    """Redact, then keep the head and tail of `text` with an explicit marker."""
    safe = redact(text)
    limit = policy.max_chars_per_step
    if len(safe) <= limit:
        return safe
    head = int(limit * policy.head_fraction)
    tail = limit - head
    elided = len(safe) - limit
    return safe[:head] + ELISION_TEMPLATE.format(elided=elided) + (safe[-tail:] if tail else "")


def _render_args(args: dict[str, Any] | None, policy: TruncationPolicy) -> str | None:
    if not args:
        return None
    text = canonical_json_bytes(args).decode("utf-8")
    # Arguments are short by nature and identify the call, so they get a
    # third of the step's budget -- enough to stay recognisable, not enough
    # to crowd out the result.
    return truncate(text, policy.with_step_budget(policy.max_chars_per_step // 3))


def _render_step(step: JudgeStepView, policy: TruncationPolicy) -> str:
    header = f"[step {step.step_idx}] {step.actor}"
    if step.tool_name:
        header += f" · {step.tool_name}"
    lines = [header]
    rendered_args = _render_args(step.tool_args, policy)
    if rendered_args is not None:
        lines.append(f"{_INDENT}args: {rendered_args}")
    lines.append(f"{_INDENT}{truncate(step.content, policy)}")
    return "\n".join(lines)


def _render_at(steps: Sequence[JudgeStepView], policy: TruncationPolicy) -> str:
    return "\n".join(_render_step(step, policy) for step in steps)


def render_trajectory(steps: Sequence[JudgeStepView], policy: TruncationPolicy) -> str:
    """Every step, in tape order, shortened uniformly until it fits the budget.

    Binary search for the largest per-step budget whose rendering fits
    `max_total_chars`; `MIN_CHARS_PER_STEP` is a floor that wins over the
    total, because exceeding a budget is recoverable and dropping a step is
    not.
    """
    if not steps:
        return ""
    rendered = _render_at(steps, policy)
    if len(rendered) <= policy.max_total_chars:
        return rendered

    low, high = MIN_CHARS_PER_STEP, policy.max_chars_per_step
    best = _render_at(steps, policy.with_step_budget(low))
    while low < high:
        middle = (low + high + 1) // 2
        candidate = _render_at(steps, policy.with_step_budget(middle))
        if len(candidate) <= policy.max_total_chars:
            best, low = candidate, middle
        else:
            high = middle - 1
    return best


ALL_AT_ONCE_SYSTEM = f"""\
You are reviewing a customer-service conversation that FAILED, to work out which single \
step caused the failure.

The conversation has three parties, and every step names the party that took it:
- `agent`  — the assistant handling the request
- `user`   — the customer
- `tool`   — a system call the agent made, and the value the system returned

The DECISIVE ERROR STEP is the single step at which something went wrong that directly \
led to the run failing. It is not simply the step where the failure became visible, and it \
is not every step that looks imperfect: it is the earliest step whose content, had it been \
different, would plausibly have changed the outcome.

Answer with ONE JSON object and nothing else. No prose before or after it, no markdown \
fence.

{{
  "decisive_step": <integer step index from the conversation>,
  "actor": "agent" | "user" | "tool",
  "reason": "<one or two sentences>",
  "ranking": [
    {{"step": <integer>, "confidence": <number between 0 and 1>, "reason": "<short>"}},
    ...
  ]
}}

Rules:
- `decisive_step` must be a step index that actually appears in the conversation.
- `ranking` lists your suspects from most to least likely, at most {RANKING_LIMIT} of them, \
with no repeated step, and with confidences that never increase down the list.
- `ranking[0].step` must equal `decisive_step`.
- Every `ranking[i].step` must appear in the conversation.
"""

ALL_AT_ONCE_USER = """\
# The task the agent was given

{task_description}

# The policy the agent had to follow

{policy}

# The conversation, in order, with the step indices as recorded

{trajectory}

# Your answer

Which single step is the decisive error step? Answer with the JSON object described above.
"""

STEP_BY_STEP_SYSTEM = """\
You are reviewing a customer-service conversation that FAILED, one step at a time, to \
work out which single step caused the failure.

The conversation has three parties, and every step names the party that took it:
- `agent`  — the assistant handling the request
- `user`   — the customer
- `tool`   — a system call the agent made, and the value the system returned

The DECISIVE ERROR STEP is the single step at which something went wrong that directly \
led to the run failing. It is not simply the step where the failure became visible.

You are shown the conversation up to and including ONE step, and asked about that step \
only. You cannot see what happens afterwards; judge only on what is in front of you.

Answer with ONE JSON object and nothing else. No prose before or after it, no markdown \
fence.

{
  "error_here": true | false,
  "confidence": <number between 0 and 1>,
  "reason": "<one or two sentences>"
}

`error_here` is true only if THIS step — the last one shown — is the decisive error step.
`confidence` is how sure you are of that verdict, whichever way it went.
"""

STEP_BY_STEP_USER = """\
# The task the agent was given

{task_description}

# The policy the agent had to follow

{policy}

# The conversation so far, in order, with the step indices as recorded

{trajectory}

# Your answer

Is step {step_idx} — the last step shown — the decisive error step? Answer with the JSON \
object described above.
"""


def build_all_at_once_prompt(
    judge_input: JudgeInput, policy: TruncationPolicy
) -> tuple[str, str]:
    """`(system, user)` for the all-at-once protocol. Deterministic given its inputs."""
    return ALL_AT_ONCE_SYSTEM, ALL_AT_ONCE_USER.format(
        task_description=redact(judge_input.task_description),
        policy=redact(judge_input.policy),
        trajectory=render_trajectory(judge_input.steps, policy),
    )


def build_step_by_step_prompt(
    judge_input: JudgeInput, *, step_idx: int, policy: TruncationPolicy
) -> tuple[str, str]:
    """`(system, user)` asking whether the decisive error is at `step_idx`.

    Only steps up to and including `step_idx` are rendered: a judge that
    could see the future would not be running the published protocol.
    """
    prefix = tuple(step for step in judge_input.steps if step.step_idx <= step_idx)
    if not prefix or prefix[-1].step_idx != step_idx:
        raise ValueError(
            f"step {step_idx} is not in run {judge_input.run_id!r}'s trajectory"
        )
    return STEP_BY_STEP_SYSTEM, STEP_BY_STEP_USER.format(
        task_description=redact(judge_input.task_description),
        policy=redact(judge_input.policy),
        trajectory=render_trajectory(prefix, policy),
        step_idx=step_idx,
    )
