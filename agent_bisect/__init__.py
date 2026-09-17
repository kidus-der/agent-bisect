"""Bisect: counterfactual replay for LLM agent failures.

Rewinds a failed agent run to step k, changes one thing, re-runs the rest,
and names the step that caused the failure.
"""
