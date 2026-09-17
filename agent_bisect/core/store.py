"""Content-addressed blob store: sha256 of canonical JSON, zstd-compressed on disk.

Every payload that reaches the store (request/response bodies, tool
results, state snapshots) is redacted first, so an NVIDIA key echoed back
in an API response or error body never lands in a blob (rule 5 in
`docs/brief/summary.md` §3). Content addressing is on the *redacted*
bytes, so `get_bytes`'s integrity check (hash of what's on disk must equal
the filename) always holds.

Layout: `<root>/blobs/<hash[:2]>/<hash[2:4]>/<hash>.zst`. Writes are
atomic (temp file + `os.replace`) and idempotent (an existing blob for a
given hash is never rewritten), so concurrent writers racing to store the
same content never corrupt each other.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import zstandard as zstd

from agent_bisect.core.config import redact

_HASH_PREFIX_LEN = 2
_HASH_SHARD_LEN = 4


class BlobCorruptionError(Exception):
    """A blob's on-disk bytes don't hash to its own filename.

    Raised by `get_bytes`/`get_json` on read — never on write, where a
    hash mismatch cannot happen because the filename is derived from the
    bytes being written.
    """


def canonical_json_bytes(obj: Any) -> bytes:
    """Canonical JSON encoding: sorted keys, no extra whitespace, UTF-8.

    Stable across dict key ordering, so hashing this output is a stable
    content hash. `obj` must already be JSON-native (the output of e.g. a
    pydantic `model_dump(mode="json")`) -- this never stringifies
    unsupported types itself, so a caller passing a non-JSON-native value
    (a raw `datetime`, a pydantic model) fails loudly instead of silently
    serializing something unintended.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    """Hex-encoded sha256 digest of `data`."""
    return hashlib.sha256(data).hexdigest()


def _blob_path(root: Path, digest: str) -> Path:
    shard_a = digest[:_HASH_PREFIX_LEN]
    shard_b = digest[_HASH_PREFIX_LEN:_HASH_SHARD_LEN]
    return root / "blobs" / shard_a / shard_b / f"{digest}.zst"


def _atomic_write_compressed(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    compressed = zstd.ZstdCompressor().compress(data)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".zst")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(compressed)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class BlobStore:
    """Content-addressed store of redacted, zstd-compressed blobs under `root`."""

    def __init__(self, root: Path) -> None:
        self._root = root
        (self._root / "blobs").mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def has(self, digest: str) -> bool:
        """True if a blob for `digest` already exists on disk."""
        return _blob_path(self._root, digest).exists()

    def put_bytes(self, data: bytes) -> str:
        """Redact, then store `data` (must be UTF-8 text) by content hash.

        Returns the hex digest of the *redacted* bytes -- the digest a
        later `get_bytes`/`get_json` call must use to retrieve it. A
        second `put_bytes` of content that redacts to the same bytes is a
        no-op (dedup): the existing blob is left untouched.
        """
        redacted = redact(data.decode("utf-8")).encode("utf-8")
        digest = sha256_hex(redacted)
        path = _blob_path(self._root, digest)
        if not path.exists():
            _atomic_write_compressed(path, redacted)
        return digest

    def put_json(self, obj: Any) -> str:
        """Canonicalize `obj` to JSON, then `put_bytes` it. Returns the hex digest."""
        return self.put_bytes(canonical_json_bytes(obj))

    def get_bytes(self, digest: str) -> bytes:
        """Read and decompress the blob for `digest`, verifying its hash.

        Raises `FileNotFoundError` if no blob exists for `digest`, and
        `BlobCorruptionError` if the decompressed bytes don't hash back to
        `digest` (on-disk corruption, or a filename that was never ours).
        """
        path = _blob_path(self._root, digest)
        if not path.exists():
            raise FileNotFoundError(f"no blob for digest {digest!r} under {self._root}")
        data = zstd.ZstdDecompressor().decompress(path.read_bytes())
        if sha256_hex(data) != digest:
            raise BlobCorruptionError(f"blob {digest!r}: on-disk content does not match hash")
        return data

    def get_json(self, digest: str) -> Any:
        """`get_bytes`, then `json.loads` the result."""
        return json.loads(self.get_bytes(digest))
