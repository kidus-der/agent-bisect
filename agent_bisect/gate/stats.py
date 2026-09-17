"""The pooled two-proportion regression rule of
`docs/decisions/0019-gate-rule.md`.

Reuses `attribution.estimate`'s Wilson/Newcombe machinery unchanged --
one interval formula for every proportion-difference this project reports,
not a second one invented for the gate. The only new arithmetic here is the
two-sided p-value the comment line also carries, which the interval alone
does not give.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

from agent_bisect.attribution.estimate import Interval, newcombe_diff_interval

#: The pre-registered floor: a regression needs both the Newcombe interval
#: entirely below 0 AND at least this many points of pooled drop.
MIN_DROP_POINTS = 0.10

CONF = 0.95


def two_proportion_p_value(x1: int, n1: int, x2: int, n2: int) -> float:
    """Two-sided p-value of the pooled two-proportion z-test on `p1` vs `p2`."""
    if n1 <= 0 or n2 <= 0:
        raise ValueError(f"both n must be positive, got n1={n1}, n2={n2}")
    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    variance = pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2)
    if variance <= 0.0:
        return 1.0 if p1 == p2 else 0.0
    z = (p1 - p2) / math.sqrt(variance)
    return 2.0 * (1.0 - NormalDist().cdf(abs(z)))


@dataclass(frozen=True, slots=True)
class GateComparison:
    """Head vs base, pooled across every scenario in one gate invocation."""

    head_passes: int
    head_n: int
    base_passes: int
    base_n: int

    def __post_init__(self) -> None:
        if self.head_n <= 0 or self.base_n <= 0:
            raise ValueError(
                f"both arms need at least one run, got head_n={self.head_n}, "
                f"base_n={self.base_n}"
            )
        for name, passes, n in (("head", self.head_passes, self.head_n), ("base", self.base_passes, self.base_n)):
            if not 0 <= passes <= n:
                raise ValueError(f"{name}_passes must be between 0 and {name}_n={n}, got {passes}")

    @property
    def head_rate(self) -> float:
        return self.head_passes / self.head_n

    @property
    def base_rate(self) -> float:
        return self.base_passes / self.base_n

    @property
    def diff(self) -> float:
        """`head - base`: negative is a drop."""
        return self.head_rate - self.base_rate

    @property
    def interval(self) -> Interval:
        """95% Newcombe interval for `head - base`."""
        return newcombe_diff_interval(
            self.head_passes, self.head_n, self.base_passes, self.base_n, conf=CONF
        )

    @property
    def p_value(self) -> float:
        return two_proportion_p_value(self.head_passes, self.head_n, self.base_passes, self.base_n)

    @property
    def is_regression(self) -> bool:
        """Both pre-registered conditions, on the same pooled counts.

        The interval must lie entirely below 0 (its upper bound negative)
        AND the point drop must reach the 10-point floor -- either alone is
        not enough (`docs/decisions/0019-gate-rule.md`).
        """
        drop = self.base_rate - self.head_rate
        return self.interval.high < 0.0 and drop >= MIN_DROP_POINTS
