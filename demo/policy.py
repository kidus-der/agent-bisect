"""Load `demo/agent_policy.yaml`: the versioned rule list a PR edits.

A rule is one decision point the scripted agent (`demo/agent.py`) consults
in a scenario (`demo/tasks.py`). `slip_probability` is drawn from a
`random.Random` the caller seeds per `(base_seed, scenario, run_index)`, so
"does this run slip on this rule" is a pure function of that seed and the
probability alone -- not of call order, so `demo.agent`'s per-scenario logic
may draw for a rule at most once per run without the result depending on
what else it did first.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any

import yaml


class PolicyError(ValueError):
    """The policy file is malformed. Raised at load time, never at run time."""


@dataclass(frozen=True, slots=True)
class Rule:
    """One ordered rule and the chance a run breaks it instead of following it."""

    id: str
    order: int
    slip_probability: float
    statement: str
    slip: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.slip_probability <= 1.0:
            raise PolicyError(
                f"rule {self.id!r}: slip_probability must be in [0, 1], "
                f"got {self.slip_probability}"
            )


@dataclass(frozen=True, slots=True)
class DemoPolicy:
    """The full ordered rule list, as one immutable document."""

    version: int
    description: str
    rules: tuple[Rule, ...]

    def __post_init__(self) -> None:
        ids = [rule.id for rule in self.rules]
        duplicates = {rule_id for rule_id in ids if ids.count(rule_id) > 1}
        if duplicates:
            raise PolicyError(f"duplicate rule id(s) in policy: {sorted(duplicates)}")

    def rule(self, rule_id: str) -> Rule:
        for candidate in self.rules:
            if candidate.id == rule_id:
                return candidate
        raise KeyError(f"no rule {rule_id!r} in this policy")

    @staticmethod
    def slips(rule: Rule, rng: Random) -> bool:
        """One deterministic draw: does this run break `rule`?

        A single `rng.random()` call, so a scenario that checks at most one
        rule per run consumes exactly one draw regardless of which rule it
        is -- the seed derivation in `demo/tasks.py` does not need to know
        how many rules a scenario might check.
        """
        return rng.random() < rule.slip_probability


def _rule_from(raw: dict[str, Any]) -> Rule:
    try:
        return Rule(
            id=str(raw["id"]),
            order=int(raw["order"]),
            slip_probability=float(raw["slip_probability"]),
            statement=str(raw["statement"]).strip(),
            slip=str(raw["slip"]).strip(),
        )
    except KeyError as exc:
        raise PolicyError(f"rule is missing required field {exc}") from None


def load_policy(path: str | Path) -> DemoPolicy:
    """Parse and validate `path` into a `DemoPolicy`. Never partially valid."""
    document = yaml.safe_load(Path(path).read_text())
    if not isinstance(document, dict):
        raise PolicyError(f"{path}: top level must be a mapping")
    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list) or not raw_rules:
        raise PolicyError(f"{path}: 'rules' must be a non-empty list")
    rules = tuple(_rule_from(raw) for raw in raw_rules)
    return DemoPolicy(
        version=int(document.get("version", 1)),
        description=str(document.get("description", "")).strip(),
        rules=rules,
    )
