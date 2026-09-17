"""Scans every git-tracked file for NVIDIA API key material.

The pattern is assembled from parts so this file never contains a literal
string that would match its own scan (a hardcoded `"nvapi-" + "x" * 20`
example would trip the pre-commit hook and this test on itself).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_KEY_PREFIX = "nvapi" + "-"
_KEY_PATTERN = re.compile(_KEY_PREFIX + r"[A-Za-z0-9_\-]{20,}")

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _tracked_files() -> list[Path]:
    result = subprocess.run(  # noqa: S603, S607 - fixed argv, no shell, no user input
        ["git", "ls-files"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [_REPO_ROOT / line for line in result.stdout.splitlines() if line]


def test_no_nvidia_api_key_in_tracked_files():
    offenders = []
    for path in _tracked_files():
        if not path.is_file():
            continue
        try:
            content = path.read_text(errors="ignore")
        except OSError:
            continue
        if _KEY_PATTERN.search(content):
            offenders.append(str(path.relative_to(_REPO_ROOT)))

    assert not offenders, f"NVIDIA API key pattern found in tracked files: {offenders}"


def test_pattern_matches_a_synthetic_key_shaped_string():
    # Sanity check that the pattern isn't accidentally too narrow to ever match.
    synthetic = _KEY_PREFIX + ("x" * 25)
    assert _KEY_PATTERN.search(f"some text {synthetic} more text")
