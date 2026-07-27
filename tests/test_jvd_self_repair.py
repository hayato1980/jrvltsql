"""Historical JVRead self-repair tests.

Recovery uses the exact filename returned by JVRead and JVFiledelete. It does
not inspect or unlink Wine cache paths directly.
"""

from unittest.mock import MagicMock

import pytest

from src.fetcher.base import FetcherError
from src.fetcher.historical import HistoricalFetcher
from src.jvlink.wrapper import JVLinkError, JVLinkWrapper


def _fetcher():
    fetcher = HistoricalFetcher.__new__(HistoricalFetcher)
    fetcher.jvlink = MagicMock()
    fetcher.jvlink.jv_file_delete.return_value = 0
    fetcher.jvlink.jv_close.return_value = 0
    fetcher.jvlink.jv_open.return_value = (0, 3, 0, "ts")
    fetcher.parser_factory = MagicMock()
    fetcher.progress_display = None
    fetcher._records_fetched = 0
    fetcher._records_parsed = 0
    fetcher._records_failed = 0
    fetcher._recoverable_read_errors = 0
    fetcher._files_processed = 0
    fetcher._total_files = 3
    fetcher._jvd_self_repair_attempts = 0
    fetcher._jvd_replay_records_remaining = 0
    fetcher._jv_open_context = ("RACE", "20260101000000", 1)
    return fetcher


@pytest.mark.parametrize("error_code", [-402, -403])
def test_read_error_deletes_exact_file_then_closes_and_reopens(error_code):
    fetcher = _fetcher()
    fetcher.jvlink.jv_read.side_effect = [
        (error_code, None, "corrupt/RACE.jvd"),
        (0, None, None),
    ]
    calls = []
    fetcher.jvlink.jv_file_delete.side_effect = lambda filename: (
        calls.append(("delete", filename)) or 0
    )
    fetcher.jvlink.jv_close.side_effect = lambda: calls.append(("close", None)) or 0
    fetcher.jvlink.jv_open.side_effect = lambda *args: (
        calls.append(("open", args)) or (0, 3, 0, "ts")
    )

    assert list(
        fetcher._fetch_and_parse(
            recover_file_error=fetcher._recover_historical_read_error,
        )
    ) == []

    assert calls == [
        ("delete", "corrupt/RACE.jvd"),
        ("close", None),
        ("open", ("RACE", "20260101000000", 1)),
    ]
    assert fetcher._jvd_self_repair_attempts == 1
    assert fetcher.get_statistics()["recoverable_read_errors"] == 1


def test_read_recovery_waits_for_redownload():
    fetcher = _fetcher()
    fetcher.jvlink.jv_open.return_value = (0, 3, 2, "ts")
    fetcher._wait_for_download = MagicMock()

    fetcher._recover_historical_read_error(-402, "corrupt/RACE.jvd")

    fetcher._wait_for_download.assert_called_once_with(download_count=2)


def test_reopen_does_not_emit_already_processed_records_twice():
    fetcher = _fetcher()
    fetcher.jvlink.jv_read.side_effect = [
        (1, b"A", "first.jvd"),
        (-402, None, "corrupt.jvd"),
        (1, b"A", "first.jvd"),
        (1, b"B", "second.jvd"),
        (0, None, None),
    ]
    fetcher.parser_factory.parse.side_effect = lambda raw: {
        "RecordSpec": "RA",
        "value": raw,
    }

    records = list(
        fetcher._fetch_and_parse(
            recover_file_error=fetcher._recover_historical_read_error,
            consume_replayed_record=fetcher._consume_replayed_record,
        )
    )

    assert [record["value"] for record in records] == [b"A", b"B"]
    assert fetcher._records_fetched == 2
    assert fetcher.parser_factory.parse.call_count == 2


def test_read_recovery_is_bounded():
    fetcher = _fetcher()

    fetcher._recover_historical_read_error(-402, "first.jvd")
    fetcher._recover_historical_read_error(-402, "second.jvd")
    with pytest.raises(FetcherError, match="after 2 self-repair retries"):
        fetcher._recover_historical_read_error(-402, "third.jvd")

    assert fetcher.jvlink.jv_file_delete.call_count == 2
    assert fetcher.jvlink.jv_close.call_count == 2
    assert fetcher.jvlink.jv_open.call_count == 2


def test_read_recovery_fails_closed_without_filename():
    fetcher = _fetcher()

    with pytest.raises(FetcherError, match="without a filename"):
        fetcher._recover_historical_read_error(-402, "")

    fetcher.jvlink.jv_file_delete.assert_not_called()
    fetcher.jvlink.jv_close.assert_not_called()


def test_read_recovery_fails_closed_without_open_context():
    fetcher = _fetcher()
    fetcher._jv_open_context = None

    with pytest.raises(FetcherError, match="no JVOpen context"):
        fetcher._recover_historical_read_error(-402, "corrupt.jvd")


def test_read_recovery_preserves_delete_failure_as_cause():
    fetcher = _fetcher()
    delete_error = JVLinkError("delete failed", error_code=-1)
    fetcher.jvlink.jv_file_delete.side_effect = delete_error

    with pytest.raises(FetcherError, match="JVFiledelete failed") as exc_info:
        fetcher._recover_historical_read_error(-402, "corrupt.jvd")

    assert exc_info.value.__cause__ is delete_error
    fetcher.jvlink.jv_close.assert_not_called()


def test_read_recovery_rejects_nonzero_delete_result():
    fetcher = _fetcher()
    fetcher.jvlink.jv_file_delete.return_value = -1

    with pytest.raises(FetcherError, match="JVFiledelete returned -1"):
        fetcher._recover_historical_read_error(-402, "corrupt.jvd")

    fetcher.jvlink.jv_close.assert_not_called()


def test_non_file_recoverable_error_does_not_restart_stream():
    fetcher = _fetcher()
    fetcher.jvlink.jv_read.side_effect = [
        (-201, None, "busy.jvd"),
        (0, None, None),
    ]

    assert list(
        fetcher._fetch_and_parse(
            recover_file_error=fetcher._recover_historical_read_error,
        )
    ) == []

    fetcher.jvlink.jv_file_delete.assert_not_called()
    fetcher.jvlink.jv_close.assert_not_called()
    fetcher.jvlink.jv_open.assert_not_called()


@pytest.mark.parametrize("error_code", [-402, -403])
def test_win32_wrapper_returns_recoverable_filename(error_code):
    wrapper = JVLinkWrapper.__new__(JVLinkWrapper)
    wrapper._is_open = True
    wrapper._jvlink = MagicMock()
    wrapper._jvlink.JVRead.return_value = (
        error_code,
        "",
        0,
        "corrupt/RACE.jvd",
    )

    assert wrapper.jv_read() == (error_code, None, "corrupt/RACE.jvd")
