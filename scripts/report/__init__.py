"""P8's deterministic report generator.

Reads only committed inputs under `data/` and `docs/gates/`, and writes
Markdown table fragments to `docs/report/tables/` and figures to
`docs/report/figures/`. Nothing here makes a network call or reads
`runs/` directly except `ledger_by_phase.py`, which is a separate,
explicitly-run script whose own output (`data/results/ledger_by_phase.json`)
is what the report actually reads. See `docs/gates/P8.md` for the
reproducibility gate this package exists to satisfy.
"""
