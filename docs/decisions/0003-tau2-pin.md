# 0003 — tau2-bench pin and install method

- **Date:** 2026-09-17, written during P0a (scaffold).

## Pin

- **Repo:** `sierra-research/tau2-bench` (MIT).
- **Pinned commit:** `2174a603f6d014ef94473ffa95957f6ce27100db` — HEAD of
  the repo's default branch at the time this was written (checked via
  `git ls-remote https://github.com/sierra-research/tau2-bench.git HEAD`).
- **Distribution name:** `tau2` (see its `pyproject.toml`); the import
  name is also `tau2`.

## Install method

Shallow-clone-by-SHA into `vendor/tau2-bench/` (git-ignored), then install
as an editable **uv path source**:

- `scripts/setup_tau2.sh` does `git init`, adds `origin`, then
  `git fetch --depth 1 origin <sha>` followed by `git checkout FETCH_HEAD`.
  This works because GitHub.com's smart-HTTP server allows fetching an
  arbitrary reachable SHA (not just refs), so the fetch stays shallow (one
  commit's worth of objects) even though we're not following a branch tip.
  The script is idempotent: re-running when the vendored checkout is
  already at the pinned SHA is a no-op; running it against a different SHA
  (a future re-pin) removes and re-clones.
- `pyproject.toml`: `dependencies` includes `"tau2"`, and
  `[tool.uv.sources]` maps it to `{ path = "vendor/tau2-bench", editable = true }`.
  `uv sync` then builds/installs it into the project's `.venv` in editable
  mode, so `import tau2` works without a separate install step.

## Domain data

tau2 needs its domain data directory (airline, retail, etc. — JSON/Markdown
task and policy files under `vendor/tau2-bench/data/`) discoverable at
runtime. tau2's own resolution (`tau2.utils.utils.DATA_DIR`) is: use
`$TAU2_DATA_DIR` if set, else derive a path from `__file__` (three parents
up from `src/tau2/utils/utils.py`, i.e. the tau2-bench repo root). For our
editable path install that fallback happens to resolve to
`vendor/tau2-bench/data`, which already exists in the checkout — so a
plain editable install is *not* missing the data the way a bare `pip
install git+https://...` (sdist/wheel build, no source tree alongside)
would be.

We still set `TAU2_DATA_DIR` explicitly, in
`agent_bisect/adapters/tau2_env.py::ensure_tau2_data_dir()`, rather than
relying on tau2's `__file__`-derived fallback: that fallback is an
implementation detail of tau2's install layout, and pinning it explicitly
means data resolution keeps working even if a future re-vendor changes how
tau2 is installed (e.g. a built wheel instead of an editable path). Call
`ensure_tau2_data_dir()` before the first `import tau2` in any process
that touches domain data.

## Dependency conflicts

tau2-bench 1.0.1 pins `litellm>=1.80.15,<1.82.7`. `agent-bisect`'s own
`litellm` bound in `pyproject.toml` was narrowed to match
(`>=1.80.15,<1.82.7`) so `uv sync` resolves one shared version rather than
two litellm installs (or a resolution failure). No other conflicts
surfaced during scaffold (`fastapi`, `httpx`, `numpy`, `python-dotenv`,
`typer` ranges overlap without narrowing).

## What is intentionally not vendored

tau2-bench's `web/` (a separate frontend) and voice-provider extras
(`tau2[voice]`, `tau2[live]`) are not installed — `agent-bisect` only
needs the core `tau2` package (`import tau2`) and the airline domain data
for P0b's rate-limit/model probes.
