.PHONY: setup test lint typecheck cov

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
