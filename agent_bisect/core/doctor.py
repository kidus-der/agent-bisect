"""Read-only diagnostic checks backing `bisect doctor`.

`run_doctor()` orchestrates every check through injected collector
callables (the side effects: subprocess, import, network). Production
code (`agent_bisect.cli`) uses the real collectors defined here; tests
pass fakes, so the whole doctor flow is exercised with no real subprocess
call, import, or network request. Pass/fail logic itself lives in small
pure `evaluate_*` functions and is tested directly against them.

Thresholds are pre-registered in `docs/decisions/0001-preregistration.md`
and are never adjusted after a result is seen.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent_bisect.core.config import Settings, redact

DEFAULT_MODELS_CONFIG_PATH = Path("config/models.toml")
DEFAULT_E2E_PATH = Path("runs/p0/e2e.json")
DEFAULT_LEDGER_PATH = Path("runs/ledger.sqlite")
#: Every role a later phase needs pinned in its run manifest.
REQUIRED_MODEL_ROLES = ("agent", "user_sim", "judge")
MIN_VALID_TOOL_CALL_RATE = 0.95
AIRLINE_PASS_RATE_RANGE = (0.35, 0.75)
SUBPROCESS_TIMEOUT_S = 10.0
NIM_REQUEST_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str


# ---- pure evaluators: given already-collected facts, decide pass/fail ----


def evaluate_key(has_key: bool) -> CheckResult:
    if has_key:
        return CheckResult("nvidia_api_key", True, "found")
    return CheckResult("nvidia_api_key", False, "NVIDIA_API_KEY not set (see .env.example)")


def evaluate_uv_python(uv_version: str | None, python_version: str) -> CheckResult:
    if not uv_version:
        return CheckResult("uv_and_python", False, "uv not found on PATH")
    # collect_uv_version() already returns the full `uv --version` output
    # (e.g. "uv 0.12.15 ..."), so don't prefix it with another "uv ".
    return CheckResult("uv_and_python", True, f"{uv_version}, python {python_version}")


def evaluate_node(node_version: str | None) -> CheckResult:
    if not node_version:
        return CheckResult("node", False, "node not found on PATH (install: brew install node)")
    return CheckResult("node", True, node_version)


def evaluate_tau2(importable: bool, airline_loaded: bool, detail: str) -> CheckResult:
    if importable and airline_loaded:
        return CheckResult("tau2", True, detail or "tau2 importable, airline domain loads")
    return CheckResult("tau2", False, detail or "tau2 import or airline domain load failed")


def evaluate_nim_reachable(reachable: bool, detail: str) -> CheckResult:
    return CheckResult("nim_reachable", reachable, detail)


def evaluate_valid_tool_call_rate(models_config: dict | None) -> CheckResult:
    if models_config is None or "valid_tool_call_rate" not in models_config:
        return CheckResult("valid_tool_call_rate", False, "not measured yet (P0b)")
    rate = models_config["valid_tool_call_rate"]
    passed = rate >= MIN_VALID_TOOL_CALL_RATE
    return CheckResult(
        "valid_tool_call_rate", passed, f"{rate:.3f} (>= {MIN_VALID_TOOL_CALL_RATE} required)"
    )


def evaluate_airline_pass_rate(models_config: dict | None) -> CheckResult:
    if models_config is None or "airline_pass_rate" not in models_config:
        return CheckResult("airline_pass_rate", False, "not measured yet (P0b)")
    rate = models_config["airline_pass_rate"]
    low, high = AIRLINE_PASS_RATE_RANGE
    passed = low <= rate <= high
    return CheckResult("airline_pass_rate", passed, f"{rate:.3f} (window [{low}, {high}])")


def evaluate_chosen_models(models_config: dict | None) -> CheckResult:
    """Every role must be filled before any later phase can pin a run manifest."""
    if models_config is None:
        return CheckResult("chosen_models", False, "config/models.toml not written yet (P0b)")
    missing = [role for role in REQUIRED_MODEL_ROLES if not models_config.get(role)]
    if missing:
        return CheckResult("chosen_models", False, f"no model chosen for: {', '.join(missing)}")
    chosen = ", ".join(f"{role}={models_config[role]}" for role in REQUIRED_MODEL_ROLES)
    return CheckResult("chosen_models", True, chosen)


def _is_numeric_reward(value: object) -> bool:
    # bool is an int subclass; a True/False "reward" is a bug, not a score.
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def evaluate_e2e_task_reward(models_config: dict | None, e2e: dict | None) -> CheckResult:
    """The gate asks for *a number*, not a good one: a reward of 0.0 still passes."""
    name = "e2e_task_reward"
    if e2e is None:
        return CheckResult(name, False, "no end-to-end τ² task recorded yet (run `doctor --live`)")
    if "error" in e2e:
        return CheckResult(name, False, f"live τ² task failed: {e2e['error']}")
    reward = e2e.get("reward")
    if not _is_numeric_reward(reward):
        return CheckResult(name, False, f"τ² returned no numeric reward (got {reward!r})")
    if models_config is None:
        return CheckResult(name, False, "config/models.toml not written yet (P0b)")
    for role in ("agent", "user_sim"):
        if e2e.get(role) != models_config.get(role):
            return CheckResult(
                name,
                False,
                f"end-to-end run used {role}={e2e.get(role)!r}, "
                f"but config/models.toml chose {models_config.get(role)!r}",
            )
    source = "live" if e2e.get("live") else "recorded"
    return CheckResult(
        name, True, f"{source} τ² airline task {e2e.get('task_id')}: reward={reward}"
    )


def load_models_config(path: Path = DEFAULT_MODELS_CONFIG_PATH) -> dict | None:
    """Read `config/models.toml`, written by P0b. Returns None if it doesn't exist yet."""
    if not path.exists():
        return None
    with path.open("rb") as f:
        return tomllib.load(f)


def load_e2e_result(path: Path = DEFAULT_E2E_PATH) -> dict | None:
    """Read the recorded end-to-end run. None when absent or unreadable."""
    if not path.exists():
        return None
    try:
        result = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return result if isinstance(result, dict) else None


# ---- collectors: the real side effects, injected so tests use fakes ----


def _run(args: list[str]) -> str | None:
    try:
        result = subprocess.run(  # noqa: S603 - fixed, non-shell argv
            args, capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT_S
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def collect_uv_version() -> str | None:
    return _run(["uv", "--version"])


def collect_node_version() -> str | None:
    if shutil.which("node") is None:
        return None
    return _run(["node", "--version"])


def collect_tau2_status() -> tuple[bool, bool, str]:
    try:
        from agent_bisect.adapters.tau2_env import ensure_tau2_data_dir

        ensure_tau2_data_dir()
        import tau2  # noqa: F401
        from tau2.domains.airline.utils import AIRLINE_TASK_SET_PATH

        airline_loaded = AIRLINE_TASK_SET_PATH.exists()
        detail = "" if airline_loaded else f"airline task set not found at {AIRLINE_TASK_SET_PATH}"
        return True, airline_loaded, detail
    except Exception as exc:  # noqa: BLE001 - any import/config failure is a failed check, not a crash
        return False, False, f"{type(exc).__name__}: {exc}"


def collect_nim_reachable(settings: Settings) -> tuple[bool, str]:
    if not settings.has_nvidia_key:
        return False, "no key to test with"
    import httpx

    assert settings.nvidia_api_key is not None
    try:
        response = httpx.get(
            f"{settings.nvidia_base_url}/models",
            headers={"Authorization": f"Bearer {settings.nvidia_api_key.get_secret_value()}"},
            timeout=NIM_REQUEST_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        return False, redact(f"{type(exc).__name__}: {exc}")
    if response.status_code == 200:
        return True, "GET /v1/models -> 200"
    return False, redact(f"GET /v1/models -> {response.status_code}")


def collect_live_e2e(models_config: dict | None) -> dict:
    """Run ONE τ² airline task end to end with the chosen models. Never raises."""
    if models_config is None:
        return {"error": "config/models.toml not written yet (P0b)"}
    from agent_bisect.adapters.tau2_e2e import run_airline_task
    from agent_bisect.core.budget import BudgetLedger

    try:
        return run_airline_task(
            agent_model=models_config["agent"],
            user_sim_model=models_config["user_sim"],
            ledger=BudgetLedger(DEFAULT_LEDGER_PATH),
        )
    except Exception as exc:  # noqa: BLE001 - a live failure is a failed check, not a crash
        return {"error": redact(f"{type(exc).__name__}: {exc}")[:400]}


def _resolve_e2e(
    live: bool,
    models_config: dict | None,
    run_live_e2e: Callable[[], dict] | None,
    load_e2e_fn: Callable[[], dict | None],
) -> dict | None:
    """`--live` runs one real task; otherwise read back the recorded one."""
    if not live:
        return load_e2e_fn()
    runner = run_live_e2e or (lambda: collect_live_e2e(models_config))
    try:
        return runner()
    except Exception as exc:  # noqa: BLE001 - a live failure is a failed check, not a crash
        return {"error": redact(f"{type(exc).__name__}: {exc}")[:400]}


def run_doctor(
    settings: Settings,
    *,
    live: bool = False,
    get_uv_version: Callable[[], str | None] = collect_uv_version,
    get_node_version: Callable[[], str | None] = collect_node_version,
    get_tau2_status: Callable[[], tuple[bool, bool, str]] = collect_tau2_status,
    get_nim_reachable: Callable[[], tuple[bool, str]] | None = None,
    load_models_config_fn: Callable[[], dict | None] = load_models_config,
    load_e2e_fn: Callable[[], dict | None] = load_e2e_result,
    run_live_e2e: Callable[[], dict] | None = None,
) -> list[CheckResult]:
    """Run every doctor check and return one `CheckResult` per check, in report order."""
    nim_check = get_nim_reachable or (lambda: collect_nim_reachable(settings))
    models_config = load_models_config_fn()

    tau2_importable, tau2_airline_loaded, tau2_detail = get_tau2_status()
    nim_reachable, nim_detail = nim_check()
    e2e = _resolve_e2e(live, models_config, run_live_e2e, load_e2e_fn)

    return [
        evaluate_key(settings.has_nvidia_key),
        evaluate_uv_python(get_uv_version(), sys.version.split()[0]),
        evaluate_node(get_node_version()),
        evaluate_tau2(tau2_importable, tau2_airline_loaded, tau2_detail),
        evaluate_nim_reachable(nim_reachable, nim_detail),
        evaluate_chosen_models(models_config),
        evaluate_valid_tool_call_rate(models_config),
        evaluate_airline_pass_rate(models_config),
        evaluate_e2e_task_reward(models_config, e2e),
    ]
