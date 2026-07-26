"""Self-repair for 0-byte .jvd corrupt-cache errors (-402).

Covers the cache-purge helper and the bounded JVOpen self-repair loop that
detects -402/-403, deletes empty .jvd files, and retries.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.fetcher.base import FetcherError
from src.fetcher.historical import HistoricalFetcher
from src.jvlink.wrapper import JVLinkError, purge_zero_byte_jvd


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


# --------------------------------------------------------------------------
# _open_with_self_repair
# --------------------------------------------------------------------------

def _fetcher():
    fetcher = HistoricalFetcher.__new__(HistoricalFetcher)
    fetcher._jvlink_cache_dir = None
    fetcher.jvlink = MagicMock()
    return fetcher


def test_open_returns_immediately_on_success():
    fetcher = _fetcher()
    fetcher.jvlink.jv_open.return_value = (0, 5, 0, "ts")

    with patch("src.jvlink.wrapper.purge_zero_byte_jvd") as purge:
        result = fetcher._open_with_self_repair("RACE", "20260101000000", 1)

    assert result == (0, 5, 0, "ts")
    purge.assert_not_called()


def test_open_self_repairs_402_then_succeeds():
    fetcher = _fetcher()
    fetcher.jvlink.jv_open.side_effect = [
        JVLinkError("JVOpen failed", error_code=-402),
        (0, 3, 0, "ts"),
    ]

    with patch("src.jvlink.wrapper.purge_zero_byte_jvd", return_value=["/cache/x.jvd"]) as purge:
        result = fetcher._open_with_self_repair("RACE", "20260101000000", 1)

    assert result == (0, 3, 0, "ts")
    purge.assert_called_once()
    assert fetcher.jvlink.jv_open.call_count == 2


def test_open_fails_when_no_zero_byte_files_to_purge():
    fetcher = _fetcher()
    fetcher.jvlink.jv_open.side_effect = JVLinkError("JVOpen failed", error_code=-402)

    with patch("src.jvlink.wrapper.purge_zero_byte_jvd", return_value=[]):
        with pytest.raises(FetcherError, match="no zero-byte .jvd"):
            fetcher._open_with_self_repair("RACE", "20260101000000", 1)

    # No point retrying if nothing was corrupt: only the initial open runs.
    assert fetcher.jvlink.jv_open.call_count == 1


def test_open_gives_up_after_bounded_retries():
    fetcher = _fetcher()
    fetcher.jvlink.jv_open.side_effect = JVLinkError("JVOpen failed", error_code=-402)

    with patch("src.jvlink.wrapper.purge_zero_byte_jvd", return_value=["/cache/x.jvd"]):
        with pytest.raises(FetcherError, match="after 2 self-repair"):
            fetcher._open_with_self_repair("RACE", "20260101000000", 1)

    # Initial attempt + JVD_SELF_REPAIR_MAX_RETRIES retries.
    assert fetcher.jvlink.jv_open.call_count == HistoricalFetcher.JVD_SELF_REPAIR_MAX_RETRIES + 1


def test_open_reraises_non_cache_errors_untouched():
    fetcher = _fetcher()
    fetcher.jvlink.jv_open.side_effect = JVLinkError("JVOpen failed", error_code=-301)

    with patch("src.jvlink.wrapper.purge_zero_byte_jvd") as purge:
        with pytest.raises(JVLinkError) as exc:
            fetcher._open_with_self_repair("RACE", "20260101000000", 1)

    assert exc.value.error_code == -301
    purge.assert_not_called()


def test_resolve_cache_dir_prefers_config_over_default():
    fetcher = _fetcher()
    fetcher._jvlink_cache_dir = "/custom/cache"
    assert str(fetcher._resolve_jvlink_cache_dir()) == "/custom/cache"
