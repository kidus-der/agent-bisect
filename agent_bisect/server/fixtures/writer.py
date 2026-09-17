"""Writes a `FixtureBundle` to `data/fixtures/*.json`.

`FixtureRepository` does **not** read these files back at request time --
it rebuilds the same bundle in memory from `build_bundle(seed)`, which is
cheap and, being pure, byte-identical to what's on disk. The files here
exist so the fixture set is inspectable and diffable in the repo, so
`scripts/export_openapi.py`-adjacent tooling (and the web team's own
fixtures, if they want static JSON during development) has something
concrete to read, and so `test_determinism` has two independent
generations to compare.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agent_bisect.server.fixtures.bundle import FixtureBundle
from agent_bisect.server.fixtures.pr_checks import to_summary
from agent_bisect.server.fixtures.serialize import to_run_detail
from agent_bisect.server.schemas_meta import MetaPayload

GENERATED_AT = "2026-09-17T00:00:00Z"
PACKAGE_VERSION = "0.1.0"
TAU2_COMMIT = "a1b2c3d4e5f6"
AGENT_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"
USER_MODEL = "meta/llama-3.1-8b-instruct"


def _dump(model: BaseModel) -> Any:
    return model.model_dump(mode="json")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=None, separators=(",", ":")) + "\n")


def build_meta(bundle: FixtureBundle) -> MetaPayload:
    return MetaPayload(
        data_source="fixture",
        simulated=True,
        package_version=PACKAGE_VERSION,
        tau2_commit=TAU2_COMMIT,
        agent_model=AGENT_MODEL,
        user_model=USER_MODEL,
        generated_at=GENERATED_AT,
    )


def write_bundle(bundle: FixtureBundle, out_dir: Path) -> None:
    _write_json(out_dir / "meta.json", _dump(build_meta(bundle)))
    _write_json(out_dir / "overview.json", _dump(bundle.overview))
    _write_json(out_dir / "runs_summary.json", [_dump(s) for s in bundle.run_summaries])
    _write_json(
        out_dir / "runs_detail.json",
        [_dump(to_run_detail(plan, bundle.judge_by_run.get(plan.run_id))) for plan in bundle.plans],
    )
    _write_json(out_dir / "benchmark.json", _dump(bundle.benchmark))
    _write_json(out_dir / "dataset.json", [_dump(e) for e in bundle.dataset_entries])
    _write_json(out_dir / "pr_checks.json", [_dump(c) for c in bundle.pr_checks])
    _write_json(
        out_dir / "pr_checks_summary.json", [_dump(to_summary(c)) for c in bundle.pr_checks]
    )
