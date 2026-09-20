| True gap | Power (judge base 0.10) | Power (0.25) | Power (0.40) |
|---|---|---|---|
| +15 pts | 0.14 | 0.12 | 0.09 |
| +25 pts | 0.40 | 0.37 | 0.37 |
| +40 pts | 0.82 | 0.79 | 0.76 |
| +55 pts | 0.95 | 0.95 | 0.96 |

_Strict test split: n=12 items, 10 task clusters. The smallest observed result that clears the gate's CI is the smallest observed result that clears the CI: Bisect right on 4 of 12 items where the judge is right on none (CI [+0.077, +0.636]). Source: `docs/findings/p5-power.md`, reproduce with `uv run python scripts/p5_power.py`._
