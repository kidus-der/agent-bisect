.PHONY: setup test lint typecheck cov web serve

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
