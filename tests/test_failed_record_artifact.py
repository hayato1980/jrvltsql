"""失敗レコード証跡: パースに失敗したレコード 1 件につき 1 行、事後に追える情報が載ること.

見るのは fetch() が出すログ行そのもの（外から見える振る舞い）で、パーサの内部構造ではない。
レコードはすべて合成（tests/fixtures/record_factory.py）で、実データの再取得を要求しない。

このテストが確認しないこと:
- driver（keibaai_cloud）のマスク済みログに出るかどうか。tee は PowerShell 側の機構で、
  ここからは見えない。ここで固定できるのは「ERROR で stdout 経路に出る」ところまで。
"""

from __future__ import annotations

import base64
from unittest.mock import MagicMock

import structlog

from src.fetcher.historical import HistoricalFetcher
from src.parser.factory import ParserFactory
from tests.fixtures.record_factory import make_se_record, make_wf_record

JV_READ_COMPLETE = 0
ARTIFACT_EVENT = "Failed record artifact"


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


def _artifacts(records: list[tuple[bytes, str]]) -> list[dict]:
    """レコードを fetch() に流し、出た証跡行だけを返す."""
    reads = [(len(buff), buff, filename) for buff, filename in records]
    reads.append((JV_READ_COMPLETE, None, None))
    fetcher = _fetcher(reads)
    with structlog.testing.capture_logs() as logs:
        list(fetcher.fetch("RACE", "20220101", "20221231", option=4))
    return [entry for entry in logs if entry.get("event") == ARTIFACT_EVENT]


def test_failed_record_artifact_names_the_file_the_record_and_the_offending_field() -> None:
    record = make_se_record(make_date="00000000")

    artifact = _artifacts([(record, "SEVM2003129920230808162730.jvd")])[0]

    assert artifact["jvd_file"] == "SEVM2003129920230808162730.jvd"
    assert artifact["record_num"] == 1
    assert artifact["record_spec"] == "SE"
    assert artifact["field"] == "MakeDate"
    assert "00000000" in artifact["value"]
    assert artifact["expected"]
    assert artifact["log_level"] == "error"


def test_failed_record_artifact_carries_the_record_bytes() -> None:
    record = make_se_record(make_date="00000000")

    artifact = _artifacts([(record, "f1.jvd")])[0]

    assert artifact["record_len"] == len(record)
    assert artifact["record_b64_truncated"] is False
    assert base64.b64decode(artifact["record_b64"]) == record


def test_long_records_are_truncated_visibly() -> None:
    record = make_se_record(make_date="00000000") + b"X" * 8192

    artifact = _artifacts([(record, "f1.jvd")])[0]

    assert artifact["record_len"] == len(record)
    assert artifact["record_b64_truncated"] is True
    assert base64.b64decode(artifact["record_b64"]) == record[:4096]


def test_a_value_with_a_newline_cannot_split_the_artifact_line() -> None:
    record = make_se_record(make_date="12\n45678")

    artifact = _artifacts([(record, "f1.jvd")])[0]

    assert "\n" not in artifact["value"]
    assert "\\n" in artifact["value"]


def test_every_failed_record_gets_its_own_artifact() -> None:
    records = [(make_se_record(make_date="00000000", umaban=f"{n:02d}"), "f1.jvd") for n in (1, 2)]

    artifacts = _artifacts(records)

    assert [a["record_num"] for a in artifacts] == [1, 2]


def test_wf_records_get_the_same_artifact() -> None:
    record = make_wf_record(make_date="00000000")

    artifact = _artifacts([(record, "f1.jvd")])[0]

    assert artifact["record_spec"] == "WF"
    assert artifact["field"] == "MakeDate"
    assert "00000000" in artifact["value"]


def test_unexpected_failures_get_an_artifact_too() -> None:
    """想定外の例外こそ事後に追う必要がある（バグの側）."""
    record = make_se_record(make_date="00000000")
    fetcher = _fetcher([(len(record), record, "f1.jvd"), (JV_READ_COMPLETE, None, None)])
    fetcher.parser_factory = MagicMock()
    fetcher.parser_factory.parse.side_effect = RuntimeError("boom")

    with structlog.testing.capture_logs() as logs:
        list(fetcher.fetch("RACE", "20220101", "20221231", option=4))

    artifact = [e for e in logs if e.get("event") == ARTIFACT_EVENT][0]
    assert artifact["failure"] == "RuntimeError"
    assert artifact["field"] is None
    assert base64.b64decode(artifact["record_b64"]) == record
