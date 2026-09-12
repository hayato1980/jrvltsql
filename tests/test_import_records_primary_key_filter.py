"""Pin the primary-key filter that `import_records` applies at flush time.

`OptimizedDataImporter` used to clean/convert each record *before* appending it
to the batch buffer, and dropped rows with an incomplete primary key there
(`importer_optimized.py:753-762`). `DataImporter` does the same clean → convert →
primary-key check → `_records_failed` increment inside `_insert_batch`
(`importer.py`), i.e. at flush time rather than at append time.

These tests pin that the difference is a scheduling detail with no observable
effect: the same rows land in the database and the same statistics come back
whatever the batch size, so flushing after every record (append-time filtering)
and buffering the whole run (flush-time filtering) are indistinguishable. That
is what let `importer_optimized.py` be deleted without porting anything.

Written and run green against the pre-deletion tree, then mutation-checked:
neutering the `_has_complete_primary_key` guard turns the batch-size tests red.
"""

import tempfile
from pathlib import Path

import pytest

from src.database.schema import SCHEMAS
from src.database.schema_types import get_table_primary_key_columns
from src.database.sqlite_handler import SQLiteDatabase
from src.importer.importer import _ORDERED_MASTER_STORAGE_TABLES, DataImporter


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
        yield SQLiteDatabase({"path": str(Path(tmpdir) / "test.db")})


def test_ra_primary_key_is_the_one_under_test():
    """Guard the fixture: the columns we blank must really be primary keys."""
    primary_keys = get_table_primary_key_columns("NL_RA")
    assert "JyoCD" in primary_keys
    assert "Kaiji" in primary_keys
    assert "NL_RA" not in _ORDERED_MASTER_STORAGE_TABLES


def test_ordered_master_tables_are_exempt_from_the_filter():
    """The guard has two arms; ordered-master storage takes the other one."""
    assert "NL_YS" in _ORDERED_MASTER_STORAGE_TABLES
    assert get_table_primary_key_columns("NL_YS")
    assert DataImporter._has_complete_primary_key("NL_RA", _ra_record(1)) is True
    assert DataImporter._has_complete_primary_key("NL_RA", _ra_record(1, JyoCD="")) is False


@pytest.mark.parametrize("batch_size", [1, 3, 100])
def test_incomplete_primary_key_is_dropped_regardless_of_batch_size(db, batch_size):
    """Rows missing a primary-key value are skipped and counted as failed.

    batch_size=1 flushes after every record, so the filter runs where the
    deleted importer ran it; batch_size=100 buffers the whole run and filters
    once at flush. Both must produce the same rows and the same counters.
    """
    records = [
        _ra_record(1),
        _ra_record(2, JyoCD=""),
        _ra_record(3),
        _ra_record(4, Kaiji=None),
    ]

    with db:
        db.execute(SCHEMAS["NL_RA"])

        importer = DataImporter(db, batch_size=batch_size)
        stats = importer.import_records(iter(records), auto_commit=False)
        db.commit()

        assert stats["records_imported"] == 2
        assert stats["records_failed"] == 2

        rows = db.fetch_all("SELECT RaceNum FROM NL_RA ORDER BY RaceNum")
        assert [row["RaceNum"] for row in rows] == [1, 3]
