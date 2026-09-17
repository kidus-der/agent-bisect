"""Six synthetic PR checks (3 regressions, 3 no-ops) for the PR-checks page.

`p_value` is a real two-proportion z-test over the fabricated pass counts
(`scipy.stats.norm`), not a hand-typed number; the rendered comment mirrors
`docs/brief/summary.md` §5's illustrative format.
"""

from __future__ import annotations

from scipy.stats import norm

from agent_bisect.server.fixtures.catalog import AIRLINE_TASKS, RETAIL_TASKS
from agent_bisect.server.fixtures.synth import pick, pick_int, seeded_rng
from agent_bisect.server.schemas_benchmark import CiValue
from agent_bisect.server.schemas_pr import PrCheckDetail, PrCheckSummary, ScenarioRow

_N_SCENARIOS = 24
_RUNS_PER_SCENARIO = 4


def _two_proportion_p_value(x1: int, n1: int, x2: int, n2: int) -> float:
    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    se = (pooled * (1 - pooled) * (1 / n1 + 1 / n2)) ** 0.5
    if se == 0:
        return 1.0
    z = (p1 - p2) / se
    return float(2 * (1 - norm.cdf(abs(z))))


def _wilson_ci(x: int, n: int) -> CiValue:
    from agent_bisect.attribution.estimate import wilson_interval

    interval = wilson_interval(x, n)
    return CiValue(
        value=round(x / n, 4), ci_low=round(interval.low, 4), ci_high=round(interval.high, 4)
    )


def _comment_markdown(
    title: str,
    base_rate: float,
    head_rate: float,
    p_value: float,
    decisive_step: int | None,
    n: int,
) -> str:
    if decisive_step is None:
        return (
            f"Bisect · no regression detected\nscenario suite     {title}\n"
            f"pass rate          base {base_rate:.2f}  ->  head {head_rate:.2f}"
            f"   (p = {p_value:.3f})\n"
            "no decisive step change · details -> bisect serve"
        )
    effect = round(base_rate - head_rate, 2)
    return (
        f"Bisect · agent regression detected\n"
        f"scenario suite     {title} ({_N_SCENARIOS} tasks x {_RUNS_PER_SCENARIO} runs)\n"
        f"pass rate          base {base_rate:.2f}  ->  head {head_rate:.2f}   (p = {p_value:.3f})\n"
        f"decisive step      step {decisive_step}\n"
        f"effect of reverting at step {decisive_step}   +{effect:.2f}\n"
        f"{n} model calls · details -> bisect serve"
    )


def _build_one(index: int, master_seed: int, is_regression: bool) -> PrCheckDetail:
    check_id = f"pr-check-{index:02d}"
    rng = seeded_rng(master_seed, check_id)
    domain_tasks = AIRLINE_TASKS if index % 2 == 0 else RETAIL_TASKS
    title = f"{pick(rng, domain_tasks)}"
    base_x, base_n = pick_int(rng, 18, 22), 24
    if is_regression:
        head_x = pick_int(rng, 10, 15)
    else:
        head_x = base_x + pick_int(rng, -1, 1)
        head_x = max(0, min(base_n, head_x))
    head_n = 24
    p_value = _two_proportion_p_value(base_x, base_n, head_x, head_n)
    decisive_step = pick_int(rng, 3, 12) if is_regression else None
    scenarios = tuple(
        ScenarioRow(
            scenario=f"{title}-{i:02d}",
            base_pass_rate=round(pick_int(rng, 60, 100) / 100, 2),
            head_pass_rate=round(
                (pick_int(rng, 20, 60) if is_regression else pick_int(rng, 60, 100)) / 100, 2
            ),
            n=_RUNS_PER_SCENARIO,
        )
        for i in range(_N_SCENARIOS)
    )
    return PrCheckDetail(
        check_id=check_id,
        pr_number=1000 + index,
        title=title,
        is_regression=is_regression,
        base_pass_rate=_wilson_ci(base_x, base_n),
        head_pass_rate=_wilson_ci(head_x, head_n),
        p_value=round(p_value, 4),
        decisive_step_base=decisive_step,
        decisive_step_head=decisive_step,
        scenarios=scenarios,
        comment_markdown=_comment_markdown(
            title, base_x / base_n, head_x / head_n, p_value, decisive_step, base_n + head_n
        ),
    )


def build_pr_checks(master_seed: int) -> tuple[PrCheckDetail, ...]:
    return tuple(_build_one(i, master_seed, is_regression=i < 3) for i in range(6))


def to_summary(detail: PrCheckDetail) -> PrCheckSummary:
    return PrCheckSummary(
        check_id=detail.check_id,
        pr_number=detail.pr_number,
        title=detail.title,
        is_regression=detail.is_regression,
        base_pass_rate=detail.base_pass_rate.value,
        head_pass_rate=detail.head_pass_rate.value,
        p_value=detail.p_value,
    )
