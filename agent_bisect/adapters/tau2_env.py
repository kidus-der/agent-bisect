"""Points tau2-bench at its vendored domain data (airline, retail, etc.).

tau2-bench is vendored at `vendor/tau2-bench/` (git-ignored, pinned commit
recorded in `docs/decisions/0003-tau2-pin.md`, re-fetched by
`scripts/setup_tau2.sh`) and installed as an editable uv path dependency,
so `import tau2` works. tau2 itself resolves its data directory from the
`TAU2_DATA_DIR` env var, falling back to a path derived from `__file__`
when unset (`tau2.utils.utils.DATA_DIR`). That fallback happens to resolve
correctly for our editable install, but this module sets the env var
explicitly so data-directory resolution does not silently depend on that
implementation detail of tau2's install layout.

Call `ensure_tau2_data_dir()` before the first `import tau2` in any
process that needs domain data.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TAU2_DATA_DIR = _REPO_ROOT / "vendor" / "tau2-bench" / "data"


def ensure_tau2_data_dir(data_dir: Path | None = None) -> Path:
    """Set `TAU2_DATA_DIR` if unset, and return the path tau2 will use.

    Never overrides an already-set `TAU2_DATA_DIR` — a caller (or a test
    fixture) may deliberately point tau2 at a different data directory.
    """
    resolved = data_dir or DEFAULT_TAU2_DATA_DIR
    os.environ.setdefault("TAU2_DATA_DIR", str(resolved))
    return Path(os.environ["TAU2_DATA_DIR"])
