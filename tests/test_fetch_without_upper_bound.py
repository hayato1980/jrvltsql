"""``fetch --to`` を省いた要求（開始点から先を全部）.

``--to`` は 1 つの値で 2 つの仕事をしている。JVOpen の読み出し終了時刻が見るのは
ファイルの作成日で、``_is_within_date_range`` が見るのはレコードの開催日。option=1/2 は
作成日基準で配信するので、開催日が要求時点より先のレコードが正当に降ってくる。

省いたときの 3 つと、省かなかったときに何も変わらないことを対で固定する。
"""

from unittest.mock import MagicMock, patch

import pytest

from src.fetcher.historical import (
    HistoricalFetcher,
    _jvopen_fromtimes,
    validate_date_range,
)
from tests.cli_test_support import CliRunner

DONE = (0, None, None)


class _Wrapper:
    def __init__(self):
        self.open_fromtimes = []
        self._reads = [(4, b"aaaa", "f1"), DONE]

    def jv_open(self, data_spec, fromtime, option):
        self.open_fromtimes.append(fromtime)
        return (0, 1, 0, "20220110000000")

    def jv_read(self):
        return self._reads.pop(0)

    def jv_close(self):
        return 0


def _fetcher(year="2026"):
    """開催日 ``{year}/01/10`` のレコードを 1 件返す fetcher."""
    f = HistoricalFetcher.__new__(HistoricalFetcher)
    f.parser_factory = MagicMock()
    f.parser_factory.parse.side_effect = lambda buff: [{"Year": year, "MonthDay": "0110"}]
    f.cache_manager = None
    f.show_progress = False
    f.progress_display = None
    f._service_key = None
    f._records_fetched = f._records_parsed = f._records_failed = 0
    f._files_processed = f._total_files = 0
    f._repaired_read_errors = 0
    f._start_time = 0.0
    f._jvd_self_repair_attempts = f._jvd_replay_records_remaining = 0
    f._open_records_baseline = 0
    f._recoverable_read_errors = 0
    f._jv_open_context = f._jv_open_last_file_timestamp = f._fetch_task_id = None
    f.jvlink = _Wrapper()
    return f


class TestValidation:
    def test_a_start_date_alone_is_accepted(self):
        validate_date_range("20260101")

    def test_the_start_date_is_still_validated(self):
        with pytest.raises(ValueError, match="real calendar date"):
            validate_date_range("20260230")

    def test_an_inverted_range_is_still_rejected(self):
        with pytest.raises(ValueError, match="must not be after"):
            validate_date_range("20260301", "20260101")


class TestJvopenGetsNoEndPoint:
    def test_no_upper_bound_opens_once_from_the_start_point(self):
        assert _jvopen_fromtimes("RACE", "20260101", None, 1) == ["20260101000000"]

    def test_an_upper_bound_still_chunks_by_calendar_year(self):
        assert len(_jvopen_fromtimes("RACE", "20240101", "20261231", 4)) == 3


class TestClientSideFilter:
    def test_no_upper_bound_keeps_a_record_dated_ahead_of_the_request(self):
        f = _fetcher(year="2027")

        assert len(list(f.fetch("RACE", "20260101", None, option=1))) == 1

    def test_an_upper_bound_still_drops_it(self):
        f = _fetcher(year="2027")

        assert list(f.fetch("RACE", "20260101", "20260131", option=1)) == []

    def test_the_drop_shows_only_as_the_fetched_parsed_gap(self):
        f = _fetcher(year="2027")

        list(f.fetch("RACE", "20260101", "20260131", option=1))

        stats = f.get_statistics()
        assert (stats["records_fetched"], stats["records_parsed"]) == (1, 0)
        assert stats["records_failed"] == 0


class TestNlCache:
    def _run(self, to_date):
        f = _fetcher()
        f.cache_manager = MagicMock()
        f.cache_manager.checkpoint_nl.return_value = 0
        list(f.fetch("RACE", "20260101", to_date, option=1))
        return f.cache_manager

    def test_no_upper_bound_never_marks_a_range_complete(self):
        """付けると has_nl_range が以後その範囲を提供側へ問い合わせなくなる."""
        manager = self._run(None)

        manager.mark_nl_range_complete.assert_not_called()
        manager.write_nl_record.assert_not_called()

    def test_an_upper_bound_still_marks_it(self):
        manager = self._run("20260131")

        manager.mark_nl_range_complete.assert_called_once()

    def test_no_upper_bound_never_asks_has_nl_range(self):
        """has_nl_range は範囲の全日付を走査する。上端が無ければ問えない."""
        f = _fetcher()
        manager = MagicMock()

        list(f.fetch_with_cache(manager, "RACE", "20260101", None, option=1))

        manager.has_nl_range.assert_not_called()
        assert f.jvlink.open_fromtimes == ["20260101000000"]


class TestBatchProcessor:
    """CLI と fetcher の間の層が上端を埋めないこと."""

    def _processor(self):
        from src.importer.batch import BatchProcessor

        fetcher = MagicMock()
        fetcher.fetch.return_value = iter([])
        fetcher.get_statistics.return_value = {"records_fetched": 0, "records_failed": 0}
        with patch("src.importer.batch.HistoricalFetcher", return_value=fetcher):
            processor = BatchProcessor(database=MagicMock(), show_progress=False)
        processor.importer = MagicMock()
        processor.importer.import_records.return_value = {"records_failed": 0}
        return processor, fetcher

    @pytest.mark.parametrize("to_date", [None, "20260821"])
    def test_the_upper_bound_reaches_the_fetcher_unchanged(self, to_date):
        processor, fetcher = self._processor()

        processor.process_date_range(
            data_spec="RACE", from_date="20260820", to_date=to_date, ensure_tables=False
        )

        assert fetcher.fetch.call_args.args == ("RACE", "20260820", to_date, 1)


class TestCli:
    ARGS = ["fetch", "--from", "20260820", "--spec", "RACE", "--db", "sqlite",
            "--no-cache", "--no-progress"]

    def _invoke(self, args):
        from pathlib import Path

        from src.cli.main import cli

        processor = MagicMock()
        processor.process_date_range.return_value = {
            "records_fetched": 0, "records_parsed": 0,
            "records_imported": 0, "records_failed": 0, "batches_processed": 0,
        }
        example = Path(__file__).resolve().parents[1] / "config" / "config.yaml.example"
        runner = CliRunner(env={"COLUMNS": "200", "TERM": "dumb"})
        with runner.isolated_filesystem():
            Path("config.yaml").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            with (
                patch("src.importer.batch.BatchProcessor", MagicMock(return_value=processor)),
                patch("src.database.create_database_from_config", MagicMock()),
                patch("src.database.schema.create_all_tables"),
            ):
                result = runner.invoke(cli, ["--config", "config.yaml", *args])
        return result, processor

    def test_fetch_runs_without_an_upper_bound(self):
        result, processor = self._invoke(self.ARGS)

        assert result.exit_code == 0, result.output
        assert processor.process_date_range.call_args.kwargs["to_date"] is None

    def test_an_upper_bound_still_reaches_the_processor(self):
        _, processor = self._invoke(self.ARGS + ["--to", "20260821"])

        assert processor.process_date_range.call_args.kwargs["to_date"] == "20260821"

    def test_the_to_caveats_are_not_printed_without_an_upper_bound(self):
        from src.cli.main import FETCH_NOTE_TO_CLIENT_FILTER

        result, _ = self._invoke(self.ARGS)

        # rich は 1 行が幅を超えると折り返すので、改行を畳んでから見る。
        assert FETCH_NOTE_TO_CLIENT_FILTER not in result.output.replace("\n", "")

    def test_a_malformed_start_date_is_still_rejected(self):
        args = [a if a != "20260820" else "20260230" for a in self.ARGS]

        result, processor = self._invoke(args)

        assert result.exit_code == 1, result.output
        processor.process_date_range.assert_not_called()
