# Example `bisect gate` PR comment

One real comment, rendered by `agent_bisect.gate.comment.render_comment`
from `scripts/gates/p7.py`'s local self-test case `demo/p7-id-slip-100`
(`demo/agent_policy.yaml`'s `use_correct_task_id.slip_probability` raised
from `0.10` to `1.00`, base = `main`), not a mock — see
`docs/gates/P7.md` for the full evidence and `docs/decisions/0019-gate-rule.md`
for the rule that decided it.

```
Bisect - agent regression detected
scenario suite     demo (8 scenarios x 4 runs)
pass rate          base 0.88  ->  head 0.44   (p = 0.000229)
decisive step      step 2 · tool -> get_users
effect of reverting at step 2   +1.00  95% CI [0.54, 1.00] · N = 8
what changed at step 2
  -    slip_probability: 0.10
  +    slip_probability: 1.0
  caused by: demo/agent_policy.yaml (this PR)
7 of 14 new failures share this step · 1344 calls · details -> bisect serve
```

Reading it: 7 of the suite's 14 new failures on this PR share the same
decisive step (`get_users`, step 2 of the scenarios that call it), which
`TruthfulToolResult` — re-executing `get_users()` against the restored,
un-faulted database — confirms with a full effect (`+1.00`, control 0/8 vs
treated 8/8) at N = 8. The other 7 new failures (the two `update_lookup`
scenarios whose target task lives only in a seeded conversation, never in
the real database, so their `use_correct_task_id` slip is an agent-decision
step rather than a tool one) are not confirmed here — `docs/decisions
/0019-gate-rule.md` explains why only the tool-step case is reliably
confirmable at this sample size, and the comment reports the honest count
(`7 of 14`) rather than folding the unconfirmed half in silently.
