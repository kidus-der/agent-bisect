"""What the frozen test split can and cannot resolve, before anything is spent.

    uv run python scripts/p5_power.py

Zero network calls, deterministic from `SEED`. Uses the real
`bench.metrics.paired_bootstrap_gap` over the real cluster structure of
the frozen manifests, so the answer is about this dataset and this
estimator rather than a textbook n.

Written and run **before any live P5 call**, because a bar whose power
nobody computed is how P4 ended up failing a criterion that was never
reachable (`docs/decisions/0009-p4-outcome-and-p5-primary.md`). Results and
what they commit us to: `docs/findings/p5-power.md`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
from agent_bisect.bench.evaluate import GATE_POINTS
from agent_bisect.bench.manifest import load_frozen
from agent_bisect.bench.metrics import paired_bootstrap_gap

SIMS = 400
RESAMPLES = 2_000
SEED = 20260918


def clusters(path: str, split: str) -> list[str]:
    items = load_frozen(Path(path)).split(split)  # type: ignore[arg-type]
    return [item.group for item in items]


def power(
    groups: list[str], p_bisect: float, p_judge: float, rng: np.random.Generator
) -> tuple[float, float, float]:
    """P(CI above 0), P(gap >= 15 points), P(both) over `SIMS` draws."""
    n = len(groups)
    above = points = both = 0
    for sim in range(SIMS):
        # Shared item difficulty, so the two arms are paired the way real
        # items are: an item nobody can solve hurts both methods.
        difficulty = rng.random(n)
        a = [bool(difficulty[i] < p_bisect) for i in range(n)]
        b = [bool(difficulty[i] < p_judge) for i in range(n)]
        gap = paired_bootstrap_gap(
            a, b, groups=groups, seed=SEED + sim, resamples=RESAMPLES
        )
        ok_ci = gap.ci_low > 0.0
        ok_points = gap.value * 100.0 >= GATE_POINTS
        above += ok_ci
        points += ok_points
        both += ok_ci and ok_points
    return above / SIMS, points / SIMS, both / SIMS


def minimum_win_margin(groups: list[str]) -> tuple[int, str]:
    """Fewest items Bisect must win (with no losses) for the CI to clear 0."""
    n = len(groups)
    for wins in range(1, n + 1):
        a = [True] * wins + [False] * (n - wins)
        b = [False] * n
        gap = paired_bootstrap_gap(a, b, groups=groups, seed=SEED, resamples=10_000)
        if gap.ci_low > 0.0:
            return wins, f"CI [{gap.ci_low:+.3f}, {gap.ci_high:+.3f}]"
    return n + 1, "never"


def main() -> None:
    rng = np.random.default_rng(SEED)
    for label, path, split in (
        ("strict test", "data/manifest.json", "test"),
        ("strict dev", "data/manifest.json", "dev"),
        ("extended test", "data/manifest_extended.json", "test"),
    ):
        groups = clusters(path, split)
        sizes = Counter(groups)
        print(
            f"\n=== {label}: n={len(groups)} items, {len(sizes)} task clusters, "
            f"sizes {sorted(sizes.values(), reverse=True)} ==="
        )
        wins, detail = minimum_win_margin(groups)
        if wins <= len(groups):
            print(
                f"  minimum clean sweep for CI>0: Bisect right on {wins}/{len(groups)} "
                f"items where the judge is right on 0 -> {detail}"
            )
        else:
            print("  CI>0 is UNREACHABLE at this n, even on a total sweep")

        if label == "strict dev":
            continue
        print(f"  {'judge':>6} {'bisect':>7} {'gap':>6} {'P(CI>0)':>9} "
              f"{'P(>=15pt)':>10} {'P(gate)':>8}")
        for p_judge in (0.10, 0.25, 0.40):
            for delta in (0.15, 0.25, 0.40, 0.55):
                p_bisect = min(0.98, p_judge + delta)
                ci, pts, both = power(groups, p_bisect, p_judge, rng)
                print(
                    f"  {p_judge:>6.2f} {p_bisect:>7.2f} {delta:>6.2f} "
                    f"{ci:>9.2f} {pts:>10.2f} {both:>8.2f}"
                )


if __name__ == "__main__":
    main()
