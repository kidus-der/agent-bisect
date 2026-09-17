"""P1 redaction acceptance test (docs/decisions/0001-preregistration.md's P1
gate: "a redaction test proves the key appears in no blob or log").

Builds a synthetic key at runtime (never a literal `nvapi-...`-shaped
string in this file, so the file doesn't trip
`tests/test_no_secrets.py`'s own scan on itself), threads it through every
payload a real recording would touch (via
`agent_bisect.core.redaction_check.record_run_with_key_everywhere`), and
then scans every artifact the recording left behind (every blob,
decompressed; the SQLite index bytes, including its WAL sidecar; and
anything written to logging/stdout/stderr during the whole sequence) for
the raw key. It must appear in none of them.
"""

from __future__ import annotations

import logging

from agent_bisect.core.redaction_check import (
    every_blob_decompressed,
    every_sqlite_file_bytes,
    key_absent_everywhere,
    record_run_with_key_everywhere,
)
from agent_bisect.core.store import BlobStore
from agent_bisect.core.tape import TapeReader

_KEY_PREFIX = "nvapi" + "-"
SYNTHETIC_KEY = _KEY_PREFIX + "A" * 64


def test_synthetic_key_appears_in_no_blob(tmp_path):
    record_run_with_key_everywhere(tmp_path, SYNTHETIC_KEY)

    for content in every_blob_decompressed(tmp_path):
        assert SYNTHETIC_KEY.encode() not in content


def test_synthetic_key_appears_in_no_sqlite_bytes(tmp_path):
    record_run_with_key_everywhere(tmp_path, SYNTHETIC_KEY)

    for raw in every_sqlite_file_bytes(tmp_path):
        assert SYNTHETIC_KEY.encode() not in raw


def test_key_absent_everywhere_reports_pass(tmp_path):
    record_run_with_key_everywhere(tmp_path, SYNTHETIC_KEY)

    passed, detail = key_absent_everywhere(tmp_path, SYNTHETIC_KEY)

    assert passed is True
    assert detail == ""


def test_key_absent_everywhere_reports_failure_for_an_unredacted_sqlite_file(tmp_path):
    # Sanity check that the scan itself would catch a real leak: write the
    # raw key straight to disk, bypassing BlobStore/TapeWriter entirely.
    (tmp_path / "blobs").mkdir()
    (tmp_path / "index.sqlite").write_text(SYNTHETIC_KEY)

    passed, detail = key_absent_everywhere(tmp_path, SYNTHETIC_KEY)

    assert passed is False
    assert "index.sqlite" in detail


def test_key_absent_everywhere_reports_failure_for_an_unredacted_blob(tmp_path):
    # Same, but for a blob written by hand without going through
    # BlobStore.put_bytes (which would have redacted it) -- named by its
    # own (unredacted) content hash so BlobStore's integrity check still
    # accepts it as a well-formed blob.
    import zstandard as zstd
    from agent_bisect.core.store import sha256_hex

    (tmp_path / "index.sqlite").touch()
    raw = SYNTHETIC_KEY.encode()
    digest = sha256_hex(raw)
    blob_path = tmp_path / "blobs" / digest[:2] / digest[2:4] / f"{digest}.zst"
    blob_path.parent.mkdir(parents=True)
    blob_path.write_bytes(zstd.ZstdCompressor().compress(raw))

    passed, detail = key_absent_everywhere(tmp_path, SYNTHETIC_KEY)

    assert passed is False
    assert "blob" in detail


def test_synthetic_key_appears_in_no_captured_log_output(tmp_path, caplog):
    with caplog.at_level(logging.DEBUG):
        record_run_with_key_everywhere(tmp_path, SYNTHETIC_KEY)

    assert SYNTHETIC_KEY not in caplog.text


def test_synthetic_key_appears_in_no_captured_stdio(tmp_path, capsys):
    record_run_with_key_everywhere(tmp_path, SYNTHETIC_KEY)

    captured = capsys.readouterr()
    assert SYNTHETIC_KEY not in captured.out
    assert SYNTHETIC_KEY not in captured.err


def test_data_recovered_through_the_reader_is_also_scrubbed(tmp_path):
    """Not just "the key is absent" -- reading the run back must not
    resurface it either (redaction happens on write, so the read path
    never has the raw key to return)."""
    record_run_with_key_everywhere(tmp_path, SYNTHETIC_KEY)

    reader = TapeReader(tmp_path)
    step = reader.get_step("run-redaction-check", 0)
    manifest = reader.get_manifest("run-redaction-check")

    assert SYNTHETIC_KEY not in (step.tool_args or {}).get("note", "")
    assert SYNTHETIC_KEY not in (step.params or {}).get("also_leaked", "")
    assert SYNTHETIC_KEY not in manifest.params.get("note", "")

    assert step.request_ref is not None
    assert step.response_ref is not None
    assert step.tool_result_ref is not None
    blobs = BlobStore(tmp_path)
    assert SYNTHETIC_KEY.encode() not in blobs.get_bytes(step.request_ref)
    assert SYNTHETIC_KEY.encode() not in blobs.get_bytes(step.response_ref)
    assert SYNTHETIC_KEY.encode() not in blobs.get_bytes(step.tool_result_ref)


def test_pattern_matches_the_synthetic_key_shaped_string():
    # Sanity check that this file's own key-shaped constant would in fact
    # be caught by config.redact -- otherwise the tests above would pass
    # vacuously.
    from agent_bisect.core.config import redact

    assert redact(SYNTHETIC_KEY) != SYNTHETIC_KEY
