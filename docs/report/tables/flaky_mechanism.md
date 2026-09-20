| Arm | What it does | DB-hash reproduction rate |
|---|---|---|
| snapshot | restore the recorded world state at a step; never re-executes the tool | 100% |
| rerun_live | re-execute the same tool calls against a live, flaky environment | 0% |

_Measured over 10 recorded runs and 30 tool steps, offline and deterministically (`tests/test_tau2_flaky.py`). The flaky-world engine mechanism, measured offline and deterministically (no provider call, no seed dependence). It is evidence for the ablation the P5 gate's flaky-world criterion asks for, not a substitute for it: data/manifest_flaky.json froze at 3 items after a bounded, infrastructure-limited collection, too few to support an interval on a difference (docs/decisions/0021-p3-outcome.md, docs/decisions/0022-p5-scope.md)._
