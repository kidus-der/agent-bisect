"""The chosen models, read from `config/models.toml`.

`scripts/decide_models.py` writes that file from the P0 measurements, by
the rules in `docs/decisions/0001-preregistration.md` §"Agent selection
rule" and `docs/decisions/0004-p0-probe-protocol.md`. This module is the
one place the choice enters the code: rule 4 of `docs/brief/summary.md`
§3 is "pin what moves — model IDs, tau2 commit, user-sim model — in the
run manifest", and a model id written into a command's default would be a
second, silent source of truth.

A missing or incomplete file raises. Falling back to a hard-coded default
would let a run be recorded against a model nobody chose, and the
manifest would say so in perfect good faith.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

DEFAULT_MODELS_PATH = Path("config/models.toml")
_REQUIRED = ("agent", "user_sim", "judge", "tau2_commit")


class MissingModelsConfigError(RuntimeError):
    """`config/models.toml` is absent, unreadable, or missing a chosen model."""


class ChosenModels(BaseModel):
    """What P0 decided. Frozen: construct a new one to change a value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    agent: str
    user_sim: str
    judge: str
    tau2_commit: str
    agent_temperature: float = 0.0
    user_temperature: float = 0.0


def _read(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text())
    except FileNotFoundError as exc:
        raise MissingModelsConfigError(
            f"no chosen-models config at {path}; run scripts/decide_models.py "
            "(P0) before recording anything"
        ) from exc
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise MissingModelsConfigError(f"could not read {path}: {exc}") from exc


def load_chosen_models(path: Path = DEFAULT_MODELS_PATH) -> ChosenModels:
    """Read the chosen models. Raises rather than guessing."""
    data = _read(path)
    missing = [key for key in _REQUIRED if not data.get(key)]
    if missing:
        raise MissingModelsConfigError(
            f"{path} does not pin {', '.join(missing)}; re-run scripts/decide_models.py"
        )
    temperatures = data.get("temperatures") or {}
    return ChosenModels(
        agent=data["agent"],
        user_sim=data["user_sim"],
        judge=data["judge"],
        tau2_commit=data["tau2_commit"],
        agent_temperature=float(temperatures.get("agent", 0.0)),
        user_temperature=float(temperatures.get("user", 0.0)),
    )
