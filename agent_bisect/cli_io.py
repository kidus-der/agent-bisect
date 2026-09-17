"""Keeping a command's stdout its own.

litellm prints to **stdout** whenever it cannot price a model — one
`Provider List: ...` banner per call, via `print`, not through logging, so
it cannot be silenced with a log level. Every NIM model is unknown to
litellm's cost map, so that is every call of every recorded run: enough to
bury a human-readable summary and enough to make `--json` unparseable.

`own_stdout()` sends everything a library prints while it is open to
stderr, where diagnostics belong, and hands back the real stdout so the
command can still speak on it — progress lines during a long batch, and
the result at the end.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stdout
from typing import TextIO


@contextmanager
def own_stdout() -> Iterator[TextIO]:
    """Redirect library chatter to stderr; yield the command's real stdout."""
    original = sys.stdout
    with redirect_stdout(sys.stderr):
        yield original


def say(stream: TextIO, message: str) -> None:
    """Write one line to `stream` and flush, so a long batch reports as it goes."""
    stream.write(f"{message}\n")
    stream.flush()
