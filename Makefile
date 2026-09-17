.PHONY: test lint typecheck cov

test:
	uv run pytest -q

lint:
	uv run ruff check .
	uv run lint-imports

typecheck:
	uv run pyright

cov:
	uv run pytest -q --cov=agent_bisect --cov-report=term-missing --cov-report=html
