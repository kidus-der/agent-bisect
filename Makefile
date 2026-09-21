.PHONY: setup test lint typecheck cov web serve reproduce-p5 reproduce reproduce-check

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
#
# P5_SPLIT names the split whose outcomes are committed under
# data/results/. It is `dev` while the test split is held (decision 0023):
# scoring the dev outcome table against the test labels is refused by
# `score_outcomes`, and rightly so -- an outcome with no label in the
# split being scored must never be counted.
P5_SPLIT ?= dev
reproduce-p5:
	uv run bisect eval --split $(P5_SPLIT) --report-only
	uv run python scripts/gates/p5.py || true
	git diff --exit-code -- data/results/p5_summary.json data/results/p5_items.json
	@echo "P5 reproduced byte-identically"

# P8's report layer, and the only half of "reproduce" a clean clone can run:
# it reads committed JSON under data/ (manifests, p5_summary.json,
# p5_items.json, the sidecars in data/results/) and never touches runs/ or
# the network. Regenerates every table and figure in docs/report.md and
# fails if the result differs from what is committed -- the actual check,
# not a promise about it.
#
# `make reproduce-p5` above is a separate, machine-local step: it needs the
# raw runs/p5/ outcome table, which is gitignored (recorded model
# transcripts are too large to commit). Run it first if you have that
# directory and want the whole chain checked end to end.
reproduce:
	uv run python scripts/report/render.py
	git diff --exit-code -- docs/report.md docs/report/ data/results/ledger_by_phase.json data/results/p4_gate.json data/results/p4_power_table.json data/results/p5_power_table.json data/results/flaky_mechanism.json data/results/p5_summary_dev.json data/results/p5_items_dev.json
	@echo "P8 reproduced byte-identically"

# Same check, with the offline claim enforced rather than merely documented:
# every new network socket in the `render.py` process raises
# (scripts/report/_offline/sitecustomize.py), the same guarantee
# pytest-socket gives the test suite. `scripts/gates/p8.py` runs the
# equivalent check in a clean clone for the actual P8 gate; this target is
# the fast local version against the working tree.
reproduce-check:
	PYTHONPATH="scripts/report/_offline:$$PYTHONPATH" $(MAKE) reproduce
	@echo "reproduce-check: offline reproduction verified (network blocked)"
