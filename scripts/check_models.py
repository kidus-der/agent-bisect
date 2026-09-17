#!/usr/bin/env python3
"""P0a model availability check: which pre-registered NIM candidates are listed, and do they answer.

Run once. Phase "P0". Budget-capped via the ledger (P0a's own limit is
20 NVIDIA API calls total, across setup and this check — see
docs/decisions/0001-preregistration.md). Makes: one `GET /v1/models` call
(not ledger-tracked — same treatment as `bisect doctor`'s `nim_reachable`
check, since it's a listing call, not a completion) plus one tiny chat
completion per *listed* candidate (`max_tokens=16`) plus one tiny
tool-call smoke test per *agent* candidate whose basic smoke succeeded.

Writes results to docs/decisions/models-availability.md. Does NOT choose
models — model selection is P0b's job (see the "Agent selection rule" in
docs/decisions/0001-preregistration.md).
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from agent_bisect.core.budget import BudgetLedger
from agent_bisect.core.config import get_settings
from agent_bisect.core.llm import LiteLLMTransport, LLMClient, LLMClientConfig, LLMRequest

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPO_ROOT / "docs" / "decisions" / "models-availability.md"
LEDGER_PATH = REPO_ROOT / "runs" / "ledger.sqlite"
TOTAL_CALL_CAP = 20
SMOKE_MAX_TOKENS = 16
TOOL_CALL_MAX_TOKENS = 64
PHASE = "P0"
MODELS_LIST_TIMEOUT_S = 15.0

AGENT_CANDIDATES = (
    "moonshotai/kimi-k2.6",
    "deepseek-ai/deepseek-v4-flash-0731",
    "nvidia/nemotron-3-super-120b-a12b",
    "z-ai/glm-5.3-flash",
)
USER_SIM_CANDIDATES = (
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "openai/gpt-oss-20b",
)
JUDGE_CANDIDATES = (
    "moonshotai/kimi-k3",
    "nvidia/nemotron-3-ultra-550b-a55b",
)
ALL_CANDIDATES = AGENT_CANDIDATES + USER_SIM_CANDIDATES + JUDGE_CANDIDATES

DUMMY_TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    },
}


@dataclass(frozen=True)
class CandidateResult:
    model: str
    role: str
    listed: bool
    close_matches: tuple[str, ...] = ()
    smoke_status: str = "skipped"
    smoke_latency_ms: float | None = None
    tool_call_ok: bool | None = None  # None = not applicable (not an agent, or smoke failed)


def role_for(model: str) -> str:
    if model in AGENT_CANDIDATES:
        return "agent"
    if model in USER_SIM_CANDIDATES:
        return "user_simulator"
    return "judge"


def fetch_listed_models(base_url: str, api_key: str) -> list[str]:
    response = httpx.get(
        f"{base_url}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=MODELS_LIST_TIMEOUT_S,
    )
    response.raise_for_status()
    return sorted(m["id"] for m in response.json().get("data", []))


def find_close_matches(model: str, listed_models: list[str]) -> tuple[str, ...]:
    """Other listed models from the same vendor/family, for a candidate that's missing."""
    vendor = model.split("/", 1)[0]
    return tuple(m for m in listed_models if m.startswith(f"{vendor}/"))


async def smoke_chat(client: LLMClient, model: str) -> tuple[str, float]:
    start = time.monotonic()
    try:
        await client.complete(
            LLMRequest(
                model=model,
                messages=({"role": "user", "content": "Reply with the single word: ok"},),
                max_tokens=SMOKE_MAX_TOKENS,
                purpose="check_models:smoke",
            ),
            phase=PHASE,
        )
    except Exception as exc:  # noqa: BLE001 - every failure mode belongs in the report
        return f"error: {type(exc).__name__}: {exc}", (time.monotonic() - start) * 1000
    return "ok", (time.monotonic() - start) * 1000


async def smoke_tool_call(client: LLMClient, model: str) -> bool:
    """One tiny tool-call smoke test: does the model actually invoke the dummy function?"""
    try:
        response = await client.complete(
            LLMRequest(
                model=model,
                messages=({"role": "user", "content": "What is the weather in Denver?"},),
                max_tokens=TOOL_CALL_MAX_TOKENS,
                tools=(DUMMY_TOOL,),
                purpose="check_models:tool_call_smoke",
            ),
            phase=PHASE,
        )
    except Exception:  # noqa: BLE001 - a failed call means "tool call not confirmed"
        return False
    choices = response.raw.get("choices") or []
    message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
    return bool(message.get("tool_calls"))


async def check_candidate(
    client: LLMClient, model: str, listed_models: list[str]
) -> CandidateResult:
    role = role_for(model)
    if model not in listed_models:
        return CandidateResult(
            model=model,
            role=role,
            listed=False,
            close_matches=find_close_matches(model, listed_models),
        )

    smoke_status, latency = await smoke_chat(client, model)
    tool_call_ok = None
    if role == "agent" and smoke_status == "ok":
        tool_call_ok = await smoke_tool_call(client, model)

    return CandidateResult(
        model=model,
        role=role,
        listed=True,
        smoke_status=smoke_status,
        smoke_latency_ms=latency,
        tool_call_ok=tool_call_ok,
    )


async def run() -> list[CandidateResult]:
    settings = get_settings()
    if not settings.has_nvidia_key:
        print("NVIDIA_API_KEY not set; cannot run availability check.", file=sys.stderr)
        raise SystemExit(1)
    assert settings.nvidia_api_key is not None
    api_key = settings.nvidia_api_key.get_secret_value()

    listed_models = fetch_listed_models(settings.nvidia_base_url, api_key)

    ledger = BudgetLedger(LEDGER_PATH, max_calls=TOTAL_CALL_CAP)
    client = LLMClient(
        LiteLLMTransport(),
        ledger,
        api_base=settings.nvidia_base_url,
        api_key=api_key,
        config=LLMClientConfig(requests_per_minute=30.0),
    )

    return [await check_candidate(client, model, listed_models) for model in ALL_CANDIDATES]


def render_markdown(results: list[CandidateResult]) -> str:
    lines = [
        "# Model availability — P0a",
        "",
        "Generated by `scripts/check_models.py`. Phase `P0`. Does not choose models — "
        "see the agent-selection rule in docs/decisions/0001-preregistration.md (P0b's job).",
        "",
        "| Model | Role | Listed | Smoke status | Latency (ms) | Tool-call ok | "
        "Close matches (if unlisted) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        latency = f"{r.smoke_latency_ms:.0f}" if r.smoke_latency_ms is not None else "-"
        tool_call = "-" if r.tool_call_ok is None else ("yes" if r.tool_call_ok else "no")
        matches = ", ".join(r.close_matches) if r.close_matches else "-"
        lines.append(
            f"| {r.model} | {r.role} | {'yes' if r.listed else 'no'} | {r.smoke_status} | "
            f"{latency} | {tool_call} | {matches} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    results = asyncio.run(run())
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_markdown(results))
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
