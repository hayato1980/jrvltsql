"""Tests for batch processor setup-range splitting decisions."""

from unittest.mock import MagicMock, call

import pytest

from src.importer.batch import BatchProcessor, _split_by_year
from src.importer.importer import DataImporter, ImporterError
from src.fetcher.historical import HistoricalFetcher
from src.database.schema import SCHEMAS
from src.database.sqlite_handler import SQLiteDatabase


def test_option_3_setup_range_splits_long_periods():
    assert BatchProcessor._should_split_setup_range("20200101", "20220101", 3) is True


def test_option_4_setup_range_does_not_split_long_periods():
    assert BatchProcessor._should_split_setup_range("20200101", "20220101", 4) is False


def test_diff_options_do_not_split_long_periods():
    assert BatchProcessor._should_split_setup_range("20200101", "20220101", 1) is False
    assert BatchProcessor._should_split_setup_range("20200101", "20220101", 2) is False


def test_historical_no_data_resets_statistics_from_previous_spec():
    fetcher = HistoricalFetcher.__new__(HistoricalFetcher)
    fetcher.show_progress = False
    fetcher.progress_display = None
    fetcher.cache_manager = None
    fetcher._service_key = None
    fetcher._records_fetched = 9
    fetcher._records_parsed = 8
    fetcher._records_failed = 1
    fetcher.jvlink = MagicMock()
    fetcher.jvlink.uses_wine = False
    fetcher.jvlink.jv_open.return_value = (-1, 0, 0, "")

    assert list(fetcher.fetch("RACE", "20260701", "20260714")) == []
    assert fetcher.get_statistics() == {
        "records_fetched": 0,
        "records_parsed": 0,
        "records_failed": 0,
        "recoverable_read_errors": 0,
        "repaired_read_errors": 0,
    }


def test_schema_preparation_failure_stops_before_fetch(monkeypatch):
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = MagicMock()
    processor.cache_manager = None
    processor.fetcher = MagicMock()
    processor.importer = MagicMock()

    def fail_schema_preparation(_database):
        raise RuntimeError("unsafe schema")

    monkeypatch.setattr(
        "src.importer.batch.create_all_tables",
        fail_schema_preparation,
    )

    with pytest.raises(RuntimeError, match="unsafe schema"):
        processor.process_date_range("RACE", "20260701", "20260714")

    processor.fetcher.fetch.assert_not_called()
    processor.importer.import_records.assert_not_called()


def test_import_rejection_fails_batch_and_rolls_back(monkeypatch):
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = MagicMock()
    processor.cache_manager = None
    processor.fetcher = MagicMock()
    processor.fetcher.fetch.return_value = iter([{"RecordSpec": "SE"}])
    processor.fetcher.get_statistics.return_value = {"records_fetched": 1}
    processor.importer = MagicMock()
    processor.importer.import_records.return_value = {
        "records_imported": 0,
        "records_failed": 1,
    }
    monkeypatch.setattr(
        "src.importer.batch.create_all_tables",
        lambda _database: None,
    )

    with pytest.raises(ImporterError, match="rejected 1 record"):
        processor.process_date_range("RACE", "20260701", "20260714")

    processor.database.rollback.assert_called_once()


def test_fetch_parse_rejection_is_not_overwritten_by_import_stats(monkeypatch):
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = MagicMock()
    processor.cache_manager = None
    processor.fetcher = MagicMock()
    processor.fetcher.fetch.return_value = iter([])
    processor.fetcher.get_statistics.return_value = {
        "records_fetched": 1,
        "records_parsed": 0,
        "records_failed": 1,
    }
    processor.importer = MagicMock()
    processor.importer.import_records.return_value = {
        "records_imported": 0,
        "records_failed": 0,
    }
    monkeypatch.setattr(
        "src.importer.batch.create_all_tables",
        lambda _database: None,
    )

    with pytest.raises(ImporterError, match="rejected 1 record"):
        processor.process_date_range("RACE", "20260701", "20260714")

    processor.database.rollback.assert_called_once()


def test_caller_managed_import_still_begins_driver_transaction(monkeypatch):
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = MagicMock()
    processor.cache_manager = None
    processor.fetcher = MagicMock()
    processor.fetcher.fetch.return_value = iter([])
    processor.fetcher.get_statistics.return_value = {
        "records_fetched": 0,
        "records_parsed": 0,
        "records_failed": 0,
    }
    processor.importer = MagicMock()
    processor.importer.import_records.return_value = {
        "records_imported": 0,
        "records_failed": 0,
    }
    monkeypatch.setattr(
        "src.importer.batch.create_all_tables",
        lambda _database: None,
    )

    processor.process_date_range(
        "RACE", "20260701", "20260714", auto_commit=False
    )

    processor.database.begin_transaction.assert_called_once_with()
    processor.database.commit.assert_not_called()


def test_import_rejection_rolls_back_earlier_successful_batch(tmp_path):
    database = SQLiteDatabase({"path": str(tmp_path / "atomic.db")})
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = database
    processor.cache_manager = None
    processor.fetcher = MagicMock()
    processor.fetcher.fetch.return_value = iter(
        [
            {
                "RecordSpec": "RA",
                "Year": "2026",
                "MonthDay": "0714",
                "JyoCD": "05",
                "Kaiji": "01",
                "Nichiji": "01",
                "RaceNum": "01",
            },
            {"RecordSpec": "UNKNOWN"},
        ]
    )
    processor.fetcher.get_statistics.return_value = {
        "records_fetched": 2,
        "records_parsed": 2,
        "records_failed": 0,
    }

    with database:
        database.execute(SCHEMAS["NL_RA"])
        database.commit()
        processor.importer = DataImporter(database, batch_size=1)

        with pytest.raises(ImporterError, match="rejected 1 record"):
            processor.process_date_range(
                "RACE",
                "20260714",
                "20260714",
                ensure_tables=False,
            )

        row_count = database.fetch_one("SELECT COUNT(*) AS count FROM NL_RA")["count"]

    assert row_count == 0


def test_multiple_specs_passes_auto_commit_without_overwriting_option():
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.process_date_range = MagicMock(return_value={"records_imported": 1})

    results = processor.process_multiple_specs(
        ["RACE"],
        "20260701",
        "20260714",
        auto_commit=False,
    )

    processor.process_date_range.assert_called_once_with(
        data_spec="RACE",
        from_date="20260701",
        to_date="20260714",
        auto_commit=False,
        ensure_tables=False,
    )
    assert results["_summary"]["failed"] == 0


def test_split_setup_commits_once_after_all_chunks_succeed():
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = MagicMock()
    processor._iter_year_chunks = MagicMock(
        return_value=iter(
            [("20200101", "20201231"), ("20210101", "20211231")]
        )
    )
    processor.process_date_range = MagicMock(
        side_effect=[
            {"records_imported": 2, "records_failed": 0},
            {"records_imported": 3, "records_failed": 0},
        ]
    )

    stats = processor._process_split_setup_range(
        "RACE", "20200101", "20211231", 3, True, False
    )

    assert stats["records_imported"] == 5
    assert all(
        call.kwargs["auto_commit"] is False
        for call in processor.process_date_range.call_args_list
    )
    processor.database.commit.assert_called_once_with()


@pytest.mark.parametrize("driver", ["pg8000", "psycopg"])
def test_split_setup_rolls_back_postgresql_transaction_on_later_failure(
    monkeypatch, driver
):
    import src.database.postgresql_handler as postgresql_handler

    database = postgresql_handler.PostgreSQLDatabase({})
    database._connection = MagicMock()
    database._cursor = MagicMock()
    monkeypatch.setattr(postgresql_handler, "DRIVER", driver)

    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = database
    processor._iter_year_chunks = MagicMock(
        return_value=iter(
            [("20200101", "20201231"), ("20210101", "20211231")]
        )
    )
    processor.process_date_range = MagicMock(
        side_effect=[{"records_imported": 1}, RuntimeError("later chunk failed")]
    )

    with pytest.raises(RuntimeError, match="later chunk failed"):
        processor._process_split_setup_range(
            "RACE", "20200101", "20211231", 3, True, False
        )

    if driver == "pg8000":
        assert database._connection.run.call_args_list == [
            call("BEGIN"),
            call("ROLLBACK"),
        ]
    else:
        database._connection.rollback.assert_called_once_with()


def test_split_setup_rolls_back_all_chunks_on_later_failure(tmp_path):
    database = SQLiteDatabase({"path": str(tmp_path / "split-atomic.db")})
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = database
    processor.cache_manager = None
    processor.fetcher = MagicMock()
    processor.fetcher.fetch.side_effect = [
        iter(
            [
                {
                    "RecordSpec": "RA",
                    "Year": "2025",
                    "MonthDay": "0714",
                    "JyoCD": "05",
                    "Kaiji": "01",
                    "Nichiji": "01",
                    "RaceNum": "01",
                }
            ]
        ),
        iter([{"RecordSpec": "UNKNOWN"}]),
    ]
    processor.fetcher.get_statistics.side_effect = [
        {"records_fetched": 1, "records_parsed": 1, "records_failed": 0},
        {"records_fetched": 1, "records_parsed": 1, "records_failed": 0},
    ]
    processor._iter_year_chunks = MagicMock(
        return_value=iter(
            [("20250101", "20251231"), ("20260101", "20261231")]
        )
    )

    with database:
        database.execute(SCHEMAS["NL_RA"])
        database.commit()
        processor.importer = DataImporter(database, batch_size=1)

        with pytest.raises(ImporterError, match="rejected 1 record"):
            processor._process_split_setup_range(
                "RACE", "20250101", "20261231", 3, True, False
            )

        row_count = database.fetch_one("SELECT COUNT(*) AS count FROM NL_RA")["count"]

    assert row_count == 0



class _RecordingFetcher:
    """Fake fetcher that replays a fixed record stream.

    ``rejects_before`` is the index of the record whose fetch also rejects one
    record -- something JV-Link returned that the parser refused, so it never
    reaches the importer. An index of ``len(records)`` rejects during the final
    pull, after the last record was already handed over.
    """

    def __init__(self, records, rejects_before=None):
        self._records = list(records)
        self._rejects_before = rejects_before
        self._records_failed = 0

    def fetch(self, *args, **kwargs):
        for index, record in enumerate(self._records):
            if index == self._rejects_before:
                self._records_failed += 1
            yield record
        if self._rejects_before == len(self._records):
            self._records_failed += 1

    def get_statistics(self):
        return {
            "records_fetched": len(self._records),
            "records_parsed": len(self._records),
            "records_failed": self._records_failed,
        }


class _RecordingImporter:
    """Fake importer that consumes each stream and records what it received."""

    def __init__(self, rejected_years=()):
        self.calls = []
        self._rejected_years = set(rejected_years)

    def import_records(self, records, auto_commit=True):
        batch = list(records)
        self.calls.append(batch)
        rejected = sum(
            1
            for record in batch
            if int(record.get("Year", 0)) in self._rejected_years
        )
        return {
            "records_imported": len(batch) - rejected,
            "records_failed": rejected,
            "batches_processed": 1,
        }


def _dated_record(year, monthday="0105"):
    return {"RecordSpec": "RA", "Year": str(year), "MonthDay": monthday}


def _year_boundary_processor(records, importer=None, rejects_before=None):
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = MagicMock()
    processor.cache_manager = None
    processor.fetcher = _RecordingFetcher(records, rejects_before=rejects_before)
    processor.importer = importer or _RecordingImporter()
    return processor


def _transaction_calls(database):
    return [name for name, _args, _kwargs in database.mock_calls]


def _commit_markers(capsys):
    return [
        line.strip()
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("[commit] year=")
    ]


def test_option_4_commits_at_each_year_boundary(capsys):
    processor = _year_boundary_processor(
        [
            _dated_record(1986, "0105"),
            _dated_record(1986, "0301"),
            _dated_record(1987, "0104"),
            _dated_record(1988, "0110"),
        ]
    )

    processor.process_date_range(
        "RACE", "19860101", "19881231", option=4, ensure_tables=False
    )

    assert _transaction_calls(processor.database).count("commit") == 3
    assert [len(batch) for batch in processor.importer.calls] == [2, 1, 1]
    assert _commit_markers(capsys) == [
        "[commit] year=1986",
        "[commit] year=1987",
        "[commit] year=1988",
    ]


def test_option_4_single_year_commits_once(capsys):
    processor = _year_boundary_processor(
        [_dated_record(2022, "0105"), _dated_record(2022, "1231")]
    )

    processor.process_date_range(
        "RACE", "20220101", "20221231", option=4, ensure_tables=False
    )

    assert _transaction_calls(processor.database).count("commit") == 1
    assert _commit_markers(capsys) == ["[commit] year=2022"]


def test_option_4_empty_stream_commits_once_without_a_marker(capsys):
    processor = _year_boundary_processor([])

    processor.process_date_range(
        "RACE", "20220101", "20221231", option=4, ensure_tables=False
    )

    assert _transaction_calls(processor.database).count("commit") == 1
    assert [len(batch) for batch in processor.importer.calls] == [0]
    assert _commit_markers(capsys) == []


@pytest.mark.parametrize("option", [1, 2])
def test_diff_options_keep_a_single_transaction_across_years(capsys, option):
    processor = _year_boundary_processor(
        [_dated_record(1986), _dated_record(1987), _dated_record(1988)]
    )

    processor.process_date_range(
        "RACE", "19860101", "19881231", option=option, ensure_tables=False
    )

    assert _transaction_calls(processor.database).count("commit") == 1
    assert [len(batch) for batch in processor.importer.calls] == [3]
    assert _commit_markers(capsys) == []


def test_option_4_undated_records_commit_once_without_a_year_marker(capsys):
    processor = _year_boundary_processor(
        [
            {"RecordSpec": "UM", "KettoNum": "1986100001"},
            {"RecordSpec": "UM", "KettoNum": "1986100002"},
        ]
    )

    processor.process_date_range(
        "BLOD", "19860101", "20221231", option=4, ensure_tables=False
    )

    assert _transaction_calls(processor.database).count("commit") == 1
    assert [len(batch) for batch in processor.importer.calls] == [2]
    assert _commit_markers(capsys) == []


def test_option_4_undated_records_join_the_surrounding_year(capsys):
    processor = _year_boundary_processor(
        [
            {"RecordSpec": "UM", "KettoNum": "1986100001"},
            _dated_record(1986),
            {"RecordSpec": "UM", "KettoNum": "1986100002"},
            _dated_record(1987),
        ]
    )

    processor.process_date_range(
        "RACE", "19860101", "19871231", option=4, ensure_tables=False
    )

    assert [len(batch) for batch in processor.importer.calls] == [3, 1]
    assert _commit_markers(capsys) == ["[commit] year=1986", "[commit] year=1987"]


def test_option_4_late_arriving_earlier_year_joins_the_current_transaction(capsys):
    processor = _year_boundary_processor(
        [
            _dated_record(1986),
            _dated_record(1987),
            _dated_record(1986, "1231"),
            _dated_record(1988),
        ]
    )

    processor.process_date_range(
        "RACE", "19860101", "19881231", option=4, ensure_tables=False
    )

    assert [len(batch) for batch in processor.importer.calls] == [1, 2, 1]
    assert _commit_markers(capsys) == [
        "[commit] year=1986",
        "[commit] year=1987",
        "[commit] year=1988",
    ]


def test_option_4_years_arriving_early_do_not_reopen_the_years_they_skipped(capsys):
    processor = _year_boundary_processor(
        [
            _dated_record(1986),
            _dated_record(1990),
            _dated_record(1987),
            _dated_record(1988),
        ]
    )

    processor.process_date_range(
        "RACE", "19860101", "19901231", option=4, ensure_tables=False
    )

    # 1987 and 1988 arrive after 1990 opened its transaction, so they are
    # committed under it. Reporting them would move the resume point back.
    assert [len(batch) for batch in processor.importer.calls] == [1, 3]
    assert _commit_markers(capsys) == ["[commit] year=1986", "[commit] year=1990"]


def test_option_4_rejection_rolls_back_only_the_failing_year(capsys):
    processor = _year_boundary_processor(
        [_dated_record(1986), _dated_record(1987), _dated_record(1988)],
        importer=_RecordingImporter(rejected_years=[1987]),
    )

    with pytest.raises(ImporterError, match="rejected 1 record"):
        processor.process_date_range(
            "RACE", "19860101", "19881231", option=4, ensure_tables=False
        )

    assert _transaction_calls(processor.database) == [
        "begin_transaction",
        "commit",
        "begin_transaction",
        "rollback",
    ]
    assert _commit_markers(capsys) == ["[commit] year=1986"]


def test_option_4_fetch_rejection_rolls_back_the_year_it_belongs_to(capsys):
    # The fetcher rejects a record while the 1987 record is being pulled, and
    # that pull is what closes 1986's transaction. The rejection belongs to
    # 1987, so 1986 must still commit.
    processor = _year_boundary_processor(
        [_dated_record(1986), _dated_record(1987)],
        rejects_before=1,
    )

    with pytest.raises(ImporterError, match="rejected 1 record"):
        processor.process_date_range(
            "RACE", "19860101", "19871231", option=4, ensure_tables=False
        )

    assert _transaction_calls(processor.database) == [
        "begin_transaction",
        "commit",
        "begin_transaction",
        "rollback",
    ]
    assert _commit_markers(capsys) == ["[commit] year=1986"]


def test_option_4_fetch_rejection_after_the_last_record_still_fails_the_run(capsys):
    processor = _year_boundary_processor(
        [_dated_record(1986)],
        rejects_before=1,
    )

    with pytest.raises(ImporterError, match="rejected 1 record"):
        processor.process_date_range(
            "RACE", "19860101", "19861231", option=4, ensure_tables=False
        )

    # No year can be charged for it, so the committed year stands and the run
    # fails: the operator re-runs, and upsert makes the re-fetch harmless.
    assert _commit_markers(capsys) == ["[commit] year=1986"]


def test_option_4_caller_managed_transaction_keeps_a_single_commit_point(capsys):
    processor = _year_boundary_processor(
        [_dated_record(1986), _dated_record(1987)]
    )

    processor.process_date_range(
        "RACE",
        "19860101",
        "19871231",
        option=4,
        auto_commit=False,
        ensure_tables=False,
    )

    assert "commit" not in _transaction_calls(processor.database)
    assert [len(batch) for batch in processor.importer.calls] == [2]
    assert _commit_markers(capsys) == []


def test_option_4_reports_combined_statistics_across_years():
    processor = _year_boundary_processor(
        [_dated_record(1986), _dated_record(1987), _dated_record(1988)]
    )

    stats = processor.process_date_range(
        "RACE", "19860101", "19881231", option=4, ensure_tables=False
    )

    assert stats["records_imported"] == 3
    assert stats["records_fetched"] == 3
    assert stats["records_failed"] == 0
    assert stats["batches_processed"] == 3


def test_option_4_year_rejection_leaves_earlier_years_in_the_database(tmp_path):
    database = SQLiteDatabase({"path": str(tmp_path / "year-boundary.db")})
    processor = BatchProcessor.__new__(BatchProcessor)
    processor.database = database
    processor.cache_manager = None
    processor.fetcher = _RecordingFetcher(
        [
            {
                "RecordSpec": "RA",
                "Year": "1986",
                "MonthDay": "0105",
                "JyoCD": "05",
                "Kaiji": "01",
                "Nichiji": "01",
                "RaceNum": "01",
            },
            {"RecordSpec": "UNKNOWN", "Year": "1987", "MonthDay": "0104"},
        ]
    )

    with database:
        database.execute(SCHEMAS["NL_RA"])
        database.commit()
        processor.importer = DataImporter(database, batch_size=1)

        with pytest.raises(ImporterError, match="rejected 1 record"):
            processor.process_date_range(
                "RACE",
                "19860101",
                "19871231",
                option=4,
                ensure_tables=False,
            )

        row_count = database.fetch_one("SELECT COUNT(*) AS count FROM NL_RA")["count"]

    assert row_count == 1


def test_split_by_year_refuses_to_advance_on_an_unconsumed_group():
    # Without this guard an importer that stops reading mid-group would leave
    # the splitter looping forever instead of failing.
    groups = _split_by_year(iter([_dated_record(1986), _dated_record(1987)]))
    next(groups)

    with pytest.raises(RuntimeError, match="abandoned"):
        next(groups)
