"""The P7 PR-check demo: a scripted, seeded, no-LLM scenario suite.

Every scenario here drives tau2's real orchestrator, environment and
evaluator (vendored "mock" domain) over sockets that stay open only to
localhost-free code -- the agent and user are both scripted, so nothing in
this package ever makes a network call. See `docs/decisions/0019-gate-rule.md`
for the suite's shape and `docs/brief/summary.md` section 5 for the PR
check this feeds.
"""

from __future__ import annotations
