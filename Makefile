.PHONY: setup test lint typecheck cov web serve reproduce-p5

# Everything a fresh clone needs. The hooks path matters most: .githooks/
# is not active until git is told about it, so a new clone has NO secret
# scanning until `make setup` runs. `bisect doctor` checks it is wired.
setup:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit
	./scripts/setup_tau2.sh
	uv sync
	@echo "setup complete -- run 'uv run bisect doctor' to verify"

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run lint-imports

typecheck:
	uv run pyright

cov:
	uv run pytest -q --cov=agent_bisect --cov-report=term-missing --cov-report=html

# Builds the dashboard into agent_bisect/server/static/, the release build
# committed at the end of P6 (docs/gates/P6.md) -- run before every release.
web:
	cd web && npm run build

# `bisect serve` needs no Node: `make web` bakes the dashboard into the
# Python package once, ahead of time.
serve:
	uv run bisect serve --fixture

# Rebuild every P5 number from stored results, offline. No judge, no fork,
# no network: `bisect eval --report-only` replays the tidy per-(item,
# method) table that the live run wrote and re-derives the report from it.
# The `git diff --exit-code` is the actual check -- if a committed number
# moved, the target fails rather than quietly rewriting it.
#
# P8's own `reproduce` should call this rather than inline it.
reproduce-p5:
	uv run bisect eval --split test --report-only
	uv run python scripts/gates/p5.py || true
	git diff --exit-code -- data/results/p5_summary.json data/results/p5_items.json
	@echo "P5 reproduced byte-identically"
