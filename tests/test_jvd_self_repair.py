"""Purge 0-byte .jvd corrupt-cache files (-402).

Covers the cache-purge helper that deletes empty .jvd files left by an
interrupted download, which otherwise make JVOpen/JVRead fail with -402.
"""

import pytest

from src.jvlink.wrapper import purge_zero_byte_jvd


# --------------------------------------------------------------------------
# purge_zero_byte_jvd
# --------------------------------------------------------------------------

def test_purge_deletes_only_zero_byte_jvd(tmp_path):
    empty1 = tmp_path / "RACE" / "empty1.jvd"
    empty1.parent.mkdir()
    empty1.write_bytes(b"")
    empty2 = tmp_path / "empty2.jvd"
    empty2.write_bytes(b"")
    nonempty = tmp_path / "good.jvd"
    nonempty.write_bytes(b"data")
    other_zero = tmp_path / "note.txt"  # 0 bytes but not .jvd
    other_zero.write_bytes(b"")

    deleted = purge_zero_byte_jvd(tmp_path)

    assert deleted == sorted([str(empty1), str(empty2)])
    assert not empty1.exists() and not empty2.exists()
    assert nonempty.exists() and other_zero.exists()


def test_purge_returns_empty_when_dir_missing(tmp_path):
    assert purge_zero_byte_jvd(tmp_path / "does-not-exist") == []


def test_purge_returns_empty_when_no_zero_byte(tmp_path):
    (tmp_path / "good.jvd").write_bytes(b"data")
    assert purge_zero_byte_jvd(tmp_path) == []
