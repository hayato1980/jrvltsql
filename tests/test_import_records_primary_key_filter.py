"""Pin the primary-key filter that `import_records` applies at flush time.

`OptimizedDataImporter` used to clean/convert each record *before* appending it
to the batch buffer, and dropped rows with an incomplete primary key there
(`importer_optimized.py:753-762`). `DataImporter` does the same clean → convert →
primary-key check → `_records_failed` increment inside `_insert_batch`
(`importer.py:8802-8857`), i.e. at flush time rather than at append time.

These tests pin that the difference is a scheduling detail with no observable
effect: the same rows land in the database and the same statistics come back
whatever the batch size, so flushing after every record (append-time filtering)
and flushing once at the end (flush-time filtering) are indistinguishable.
They are what lets `importer_optimized.py` be deleted without porting anything.
"""

import tempfile
from pathlib import Path

import pytest

from src.database.schema import SCHEMAS
from src.database.schema_types import get_table_primary_key_columns
from src.database.sqlite_handler import SQLiteDatabase
from src.importer.importer import DataImporter


def _ra_record(race_num, **overrides):
    """Build a valid NL_RA record, overridable to break its primary key."""
    record = {
        "headRecordSpec": "RA",
        "RecordSpec": "RA",
        "DataKubun": "1",
        "MakeDate": "20240601",
        "Year": 2024,
        "MonthDay": 601,
        "JyoCD": "06",
        "Kaiji": 3,
        "Nichiji": 8,
        "RaceNum": race_num,
        "Hondai": f"レース{race_num}",
        "Kyori": 2000,
    }
    record.update(overrides)
    return record


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmpdir:
        database = SQLiteDatabase({"path": str(Path(tmpdir) / "test.db")})
        yield database


def test_ra_primary_key_is_the_one_under_test():
    """Guard the fixture: JyoCD must really be part of NL_RA's primary key."""
    assert "JyoCD" in get_table_primary_key_columns("NL_RA")


@pytest.mark.parametrize("batch_size", [1, 2, 10])
def test_incomplete_primary_key_is_dropped_regardless_of_batch_size(db, batch_size):
    """A row missing a primary-key value is skipped and counted as failed.

    batch_size=1 flushes after every record, so the filter runs at append time;
    batch_size=10 buffers the whole run and filters once at flush. Both must
    produce the same rows and the same counters.
    """
    records = [
        _ra_record(1),
        _ra_record(2, JyoCD=""),
        _ra_record(3),
    ]

    with db:
        db.execute(SCHEMAS["NL_RA"])

        importer = DataImporter(db, batch_size=batch_size)
        stats = importer.import_records(iter(records), auto_commit=False)
        db.commit()

        assert stats["records_imported"] == 2
        assert stats["records_failed"] == 1

        rows = db.fetch_all("SELECT RaceNum FROM NL_RA ORDER BY RaceNum")
        assert [row["RaceNum"] for row in rows] == [1, 3]


def test_batch_size_does_not_change_the_outcome(db):
    """Flush-time and append-time filtering are indistinguishable end to end."""
    records = [_ra_record(1), _ra_record(2, JyoCD=""), _ra_record(3), _ra_record(4, Kaiji=None)]

    outcomes = []
    for batch_size in (1, 3, 100):
        with tempfile.TemporaryDirectory() as tmpdir:
            database = SQLiteDatabase({"path": str(Path(tmpdir) / f"{batch_size}.db")})
            with database:
                database.execute(SCHEMAS["NL_RA"])
                importer = DataImporter(database, batch_size=batch_size)
                stats = importer.import_records(iter(list(records)), auto_commit=False)
                database.commit()
                rows = database.fetch_all("SELECT RaceNum FROM NL_RA ORDER BY RaceNum")
                outcomes.append(
                    (
                        stats["records_imported"],
                        stats["records_failed"],
                        [row["RaceNum"] for row in rows],
                    )
                )

    assert outcomes[0] == outcomes[1] == outcomes[2]
    assert outcomes[0] == (2, 2, [1, 3])
