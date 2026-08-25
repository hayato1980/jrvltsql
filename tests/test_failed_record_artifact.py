"""パースに失敗したレコードを、あとから同定して再生できる形でログに残すこと.

見るのは fetch() が出すログ行そのもので、パーサの内部構造ではない。レコードは
すべて合成（tests/fixtures/record_factory.py）で、実データの再取得を要求しない。

このテストが確認しないこと:
- どのフィールドのどの値で弾かれたか。それはパーサ自身が出す行に載る（この行が
  持つのは、どのレコードだったかと、その中身）。
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import structlog

from src.fetcher.historical import HistoricalFetcher
from src.parser.factory import ParserFactory
from tests.fixtures.record_factory import make_se_record

JV_READ_COMPLETE = 0
FAILED_RECORD_EVENT = "Failed to parse record"


def _fetcher(jv_read_results) -> HistoricalFetcher:
    """JV-Link を持たない HistoricalFetcher（本物の ParserFactory を通す）."""
    f = HistoricalFetcher.__new__(HistoricalFetcher)
    f.parser_factory = ParserFactory()
    f.cache_manager = None
    f.show_progress = False
    f.progress_display = None
    f._service_key = None
    f._records_fetched = f._records_parsed = f._records_failed = 0
    f._files_processed = f._total_files = 0
    f._start_time = 0.0
    f._jvd_self_repair_attempts = f._jvd_replay_records_remaining = 0
    f._recoverable_read_errors = 0
    f._jv_open_context = f._jv_open_last_file_timestamp = f._fetch_task_id = None

    f.jvlink = MagicMock()
    f.jvlink.jv_init.return_value = None
    f.jvlink.jv_open.return_value = (0, len(jv_read_results), 0, "20220110000000")
    f.jvlink.jv_read.side_effect = jv_read_results
    return f


def _failures(records: list[tuple[bytes, str]]) -> list[dict]:
    reads = [(len(buff), buff, filename) for buff, filename in records]
    reads.append((JV_READ_COMPLETE, None, None))
    fetcher = _fetcher(reads)
    with structlog.testing.capture_logs() as logs:
        list(fetcher.fetch("RACE", "20220101", "20221231", option=4))
    return [entry for entry in logs if entry.get("event") == FAILED_RECORD_EVENT]


def test_a_failed_record_names_the_file_it_arrived_in() -> None:
    record = make_se_record(month_day="0231")

    failure = _failures([(record, "SEVM2003129920230808162730.jvd")])[0]

    assert failure["jvd_file"] == "SEVM2003129920230808162730.jvd"
    assert failure["record_num"] == 1
    assert failure["record_spec"] == "SE"
    assert failure["log_level"] == "error"


def test_a_failed_record_carries_its_own_bytes() -> None:
    record = make_se_record(month_day="0231")

    failure = _failures([(record, "f1.jvd")])[0]

    assert failure["record_len"] == len(record)
    assert failure["record_b64_truncated"] is False
    assert base64.b64decode(failure["record_b64"]) == record


def test_long_records_are_truncated_visibly() -> None:
    record = make_se_record(month_day="0231") + b"X" * 8192

    failure = _failures([(record, "f1.jvd")])[0]

    assert failure["record_len"] == len(record)
    assert failure["record_b64_truncated"] is True
    assert base64.b64decode(failure["record_b64"]) == record[:4096]


def test_every_failed_record_is_logged_separately() -> None:
    records = [(make_se_record(month_day="0231", umaban=f"{n:02d}"), "f1.jvd") for n in (1, 2)]

    failures = _failures(records)

    assert [f["record_num"] for f in failures] == [1, 2]


def test_cached_records_are_logged_the_same_way() -> None:
    """キャッシュ再生経路も同じ失敗で、同じ困り方をする."""
    record = make_se_record(month_day="0231")
    cache = MagicMock()
    cache.has_nl_range.return_value = True
    cache.read_nl.return_value = iter([record])
    fetcher = _fetcher([(JV_READ_COMPLETE, None, None)])

    with structlog.testing.capture_logs() as logs:
        list(fetcher.fetch_with_cache(cache, "RACE", "20220101", "20221231", option=4))

    failure = [e for e in logs if e.get("event") == FAILED_RECORD_EVENT][0]
    assert failure["jvd_file"] == "cache:RACE"
    assert base64.b64decode(failure["record_b64"]) == record


def test_an_unexpected_error_keeps_the_record_too() -> None:
    record = make_se_record()
    fetcher = _fetcher([(len(record), record, "f1.jvd"), (JV_READ_COMPLETE, None, None)])
    fetcher.parser_factory = MagicMock()
    fetcher.parser_factory.parse.side_effect = RuntimeError("boom")

    with structlog.testing.capture_logs() as logs:
        list(fetcher.fetch("RACE", "20220101", "20221231", option=4))

    failure = [e for e in logs if e.get("event") == FAILED_RECORD_EVENT][0]
    assert failure["error"] == "boom"
    assert base64.b64decode(failure["record_b64"]) == record
