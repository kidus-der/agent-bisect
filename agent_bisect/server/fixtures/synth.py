"""Small deterministic-draw helpers shared by every fixture generator module.

Every function here takes an explicit `numpy.random.Generator` -- nothing
reads or writes global RNG state, which is what makes `build_bundle(seed)`
byte-deterministic (`tests/server/test_fixtures.py::test_determinism`).
"""

from __future__ import annotations

import hashlib

import numpy as np

_ID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
_SEED_BYTES = 4


def _stable_seed(part: str | int) -> int:
    """A `hash()`-free digest of `part`, stable across processes and platforms.

    `hash()` on `str`/bytes is salted per-process (PYTHONHASHSEED) unless
    explicitly disabled, which would make fixture generation depend on the
    interpreter's hash seed rather than only `seed` -- exactly what
    `test_determinism` (running the generator as two separate subprocesses)
    is there to catch.
    """
    digest = hashlib.blake2b(str(part).encode(), digest_size=_SEED_BYTES).digest()
    return int.from_bytes(digest, "big")


def seeded_rng(*parts: str | int) -> np.random.Generator:
    """A fresh generator derived from `parts`, independent of any other draw.

    Used to key a step's synthetic payload off `(run_id, step_idx)` so the
    step inspector can regenerate the same payload on every request without
    the generator having stored it anywhere.
    """
    return np.random.default_rng([_stable_seed(part) for part in parts])


def random_id(rng: np.random.Generator, length: int = 6) -> str:
    """A tau2-flavoured record id, e.g. `NM1VX1`."""
    indices = rng.integers(0, len(_ID_ALPHABET), size=length)
    return "".join(_ID_ALPHABET[i] for i in indices)


def pick[S: str](rng: np.random.Generator, options: tuple[S, ...]) -> S:
    """Generic over the option type so a caller passing a `tuple[FaultType, ...]`
    (or any other `str`-based `Literal` tuple) gets that narrower type back,
    not a widened plain `str`."""
    return options[int(rng.integers(0, len(options)))]


def pick_int(rng: np.random.Generator, low: int, high: int) -> int:
    """Inclusive of both ends."""
    return int(rng.integers(low, high, endpoint=True))
