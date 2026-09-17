"""Keeping a command's stdout its own.

litellm prints to **stdout** whenever it cannot price a model — one
`Provider List: ...` banner per call, via `print`, not through logging, so
it cannot be silenced with a log level. Every NIM model is unknown to
litellm's cost map, so that is every call of every recorded run: enough to
bury a human-readable summary and enough to make `--json` unparseable.

`own_stdout()` sends everything a library prints while it is open to
stderr, where diagnostics belong, leaving stdout for what the command
itself chose to say.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout


@contextmanager
def own_stdout() -> Iterator[None]:
    """Redirect library chatter to stderr for the duration of the block."""
    with redirect_stdout(sys.stderr):
        yield
