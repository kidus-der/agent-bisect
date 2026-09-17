"""Tests for agent_bisect.core.store: the content-addressed blob store."""

from __future__ import annotations

import json

import pytest
from agent_bisect.core.store import (
    BlobCorruptionError,
    BlobStore,
    canonical_json_bytes,
    sha256_hex,
)
from hypothesis import given
from hypothesis import strategies as st

FAKE_KEY = "nvapi-" + "a" * 40

_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(),
)
_json_values = st.recursive(
    _json_scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=5),
        st.dictionaries(st.text(), children, max_size=5),
    ),
    max_leaves=10,
)


# ---- canonical_json_bytes / sha256_hex ----


def test_canonical_json_bytes_has_no_extra_whitespace():
    encoded = canonical_json_bytes({"b": 1, "a": 2})

    assert encoded == b'{"a":2,"b":1}'


@given(st.dictionaries(st.text(min_size=1), _json_scalars, min_size=1, max_size=8))
def test_canonical_json_bytes_is_stable_under_key_reordering(mapping):
    reordered = dict(reversed(list(mapping.items())))

    assert canonical_json_bytes(mapping) == canonical_json_bytes(reordered)


@given(_json_values)
def test_canonical_json_bytes_round_trips_through_json(value):
    assert json.loads(canonical_json_bytes(value)) == value


def test_sha256_hex_is_deterministic():
    assert sha256_hex(b"hello") == sha256_hex(b"hello")


def test_sha256_hex_differs_for_different_input():
    assert sha256_hex(b"hello") != sha256_hex(b"world")


# ---- BlobStore ----


def test_put_bytes_then_get_bytes_round_trips(tmp_path):
    store = BlobStore(tmp_path)

    digest = store.put_bytes(b"hello world")

    assert store.get_bytes(digest) == b"hello world"


def test_put_json_then_get_json_round_trips(tmp_path):
    store = BlobStore(tmp_path)
    payload = {"model": "some/model", "messages": [{"role": "user", "content": "hi"}]}

    digest = store.put_json(payload)

    assert store.get_json(digest) == payload


def test_has_is_false_before_put_and_true_after(tmp_path):
    store = BlobStore(tmp_path)
    digest = sha256_hex(b"not stored yet")

    assert store.has(digest) is False

    stored_digest = store.put_bytes(b"not stored yet")

    assert stored_digest == digest
    assert store.has(digest) is True


def test_put_bytes_dedups_identical_content(tmp_path):
    store = BlobStore(tmp_path)

    digest1 = store.put_bytes(b"same content")
    digest2 = store.put_bytes(b"same content")

    assert digest1 == digest2
    blob_files = list((tmp_path / "blobs").glob("**/*.zst"))
    assert len(blob_files) == 1


def test_put_bytes_shards_by_hash_prefix(tmp_path):
    store = BlobStore(tmp_path)

    digest = store.put_bytes(b"shard me")

    expected = tmp_path / "blobs" / digest[:2] / digest[2:4] / f"{digest}.zst"
    assert expected.exists()


def test_get_bytes_raises_file_not_found_for_unknown_digest(tmp_path):
    store = BlobStore(tmp_path)

    with pytest.raises(FileNotFoundError):
        store.get_bytes("0" * 64)


def test_get_bytes_raises_blob_corruption_error_on_hash_mismatch(tmp_path):
    store = BlobStore(tmp_path)
    digest = store.put_bytes(b"original content")
    blob_path = tmp_path / "blobs" / digest[:2] / digest[2:4] / f"{digest}.zst"

    # Corrupt the stored blob so its decompressed content no longer hashes
    # to its own filename -- simulates on-disk bit rot / tampering.
    import zstandard as zstd

    tampered = zstd.ZstdCompressor().compress(b"tampered content")
    blob_path.write_bytes(tampered)

    with pytest.raises(BlobCorruptionError):
        store.get_bytes(digest)


def test_blobs_are_compressed_on_disk(tmp_path):
    store = BlobStore(tmp_path)
    payload = b"x" * 10_000  # highly compressible

    digest = store.put_bytes(payload)

    blob_path = tmp_path / "blobs" / digest[:2] / digest[2:4] / f"{digest}.zst"
    assert blob_path.stat().st_size < len(payload)


def test_put_bytes_leaves_no_temp_file_behind(tmp_path):
    store = BlobStore(tmp_path)

    store.put_bytes(b"clean up after yourself")

    leftovers = list(tmp_path.glob("**/.tmp-*"))
    assert leftovers == []


def test_root_property_returns_the_configured_root(tmp_path):
    store = BlobStore(tmp_path)

    assert store.root == tmp_path


def test_put_bytes_cleans_up_temp_file_on_write_failure(tmp_path, monkeypatch):
    import os

    store = BlobStore(tmp_path)
    real_replace = os.replace

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError):
        store.put_bytes(b"never lands on disk")

    monkeypatch.setattr(os, "replace", real_replace)
    assert list(tmp_path.glob("**/.tmp-*")) == []


# ---- redaction ----


def test_put_bytes_redacts_key_before_storing(tmp_path):
    store = BlobStore(tmp_path)
    payload = json.dumps({"error": f"upstream said: key {FAKE_KEY} invalid"}).encode("utf-8")

    digest = store.put_bytes(payload)

    stored = store.get_bytes(digest)
    assert FAKE_KEY not in stored.decode("utf-8")
    assert b"nvapi-***REDACTED***" in stored


def test_put_json_redacts_key_in_nested_payload(tmp_path):
    store = BlobStore(tmp_path)
    payload = {
        "messages": [{"role": "system", "content": f"Authorization: Bearer {FAKE_KEY}"}],
    }

    digest = store.put_json(payload)

    raw = store.get_bytes(digest)
    assert FAKE_KEY not in raw.decode("utf-8")


def test_redacted_key_never_reaches_the_blob_file_on_disk(tmp_path):
    store = BlobStore(tmp_path)

    digest = store.put_bytes(f"leaked key: {FAKE_KEY}".encode())

    blob_path = tmp_path / "blobs" / digest[:2] / digest[2:4] / f"{digest}.zst"
    raw_disk_bytes = blob_path.read_bytes()  # still zstd-compressed
    assert FAKE_KEY.encode() not in raw_disk_bytes
