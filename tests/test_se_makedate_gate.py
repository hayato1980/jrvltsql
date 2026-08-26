#!/usr/bin/env python
"""SE MakeDate is a real date or the provider's exact zero sentinel.

``fixtures/captured_records/se_cancelled_race.bin`` is real provider data, not
a synthesized record. It is one of the twelve SE records of the cancelled race
at 中山 2003-12-27 10R whose MakeDate is ``00000000``; calendar-checking that
cell stopped a full 1986-2026 backfill at its 2004 chunk. All twelve share the
same header and differ only in the per-horse span, so one record is enough.
"""

import hashlib
import os
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.setup_pg_test_db import postgresql_test_config
from src.database.migration import SchemaMigrationError
from src.database.schema import SCHEMAS
from src.database.schema_jravan import JRAVAN_SCHEMAS
from src.database.sqlite_handler import SQLiteDatabase
from src.importer.importer import DataImporter, validate_import_record_header
from src.parser.se_parser import SEParser

CAPTURED_RECORDS_DIR = Path(__file__).parent / "fixtures" / "captured_records"
CANCELLED_RACE_SE = (CAPTURED_RECORDS_DIR / "se_cancelled_race.bin").read_bytes()


def _key_fields(**overrides: str) -> dict[str, str]:
    record = {
        "MakeDate": "20040115",
        "Year": "2003",
        "MonthDay": "1227",
        "JyoCD": "06",
        "Kaiji": "06",
        "Nichiji": "07",
        "RaceNum": "10",
        "Umaban": "01",
        "KettoNum": "1995107789",
    }
    record.update(overrides)
    return record


def test_the_captured_record_is_the_one_the_backfill_stopped_on() -> None:
    assert len(CANCELLED_RACE_SE) == SEParser.RECORD_LENGTH
    assert hashlib.sha256(CANCELLED_RACE_SE).hexdigest() == (
        "98d77576c1c4ea2a05dc03e6b12a11f4bacaa0c32941b33fcd784e6556540fd1"
    )


def test_cancelled_race_record_with_unset_make_date_is_parsed() -> None:
    parsed = SEParser().parse(CANCELLED_RACE_SE)

    assert parsed is not None
    assert parsed["MakeDate"] == "00000000"
    assert parsed["DataKubun"] == "9"
    assert parsed["Year"] == "2003"
    assert parsed["MonthDay"] == "1227"
    assert parsed["JyoCD"] == "06"
    assert parsed["Umaban"] == "01"
    assert parsed["KettoNum"] == "1995107789"
    assert parsed["Bamei"] == "メジロアトラス"


@pytest.mark.parametrize("make_date", ["20040115", "00000000"])
def test_make_date_accepts_a_real_date_or_the_exact_zero_sentinel(make_date: str) -> None:
    SEParser.validate_key_fields(_key_fields(MakeDate=make_date))


@pytest.mark.parametrize("make_date", ["20040231", "20040001", "20041332"])
def test_make_date_rejects_an_impossible_nonzero_date(make_date: str) -> None:
    with pytest.raises(
        ValueError,
        match="SE MakeDate must be a real yyyymmdd date or 00000000",
    ):
        SEParser.validate_key_fields(_key_fields(MakeDate=make_date))


@pytest.mark.parametrize("make_date", ["", "0000000", "000000000", "0000000A"])
def test_make_date_still_has_to_be_eight_ascii_digits(make_date: str) -> None:
    with pytest.raises(ValueError, match="SE MakeDate must be exactly 8 ASCII digits"):
        SEParser.validate_key_fields(_key_fields(MakeDate=make_date))


def test_the_race_date_gate_still_demands_a_real_date() -> None:
    with pytest.raises(ValueError, match="SE Year and MonthDay must form a real date"):
        SEParser.validate_key_fields(_key_fields(MonthDay="0000"))


def test_the_cancelled_race_record_survives_the_import_gate() -> None:
    parsed = SEParser().parse(CANCELLED_RACE_SE)

    assert validate_import_record_header(parsed) == ("SE", "9")


def test_the_cancelled_race_record_lands_in_storage(tmp_path) -> None:
    parsed = SEParser().parse(CANCELLED_RACE_SE)
    database = SQLiteDatabase({"path": str(tmp_path / "sentinel.db")})
    with database:
        database.execute(SCHEMAS["NL_SE"])
        database.commit()
        stats = DataImporter(database).import_records(iter([parsed]))
        stored = database.fetch_all("SELECT MakeDate, DataKubun, Bamei FROM NL_SE")

    assert stats["records_failed"] == 0
    assert stats["records_imported"] == 1
    assert stored == [{"MakeDate": "00000000", "DataKubun": "9", "Bamei": "メジロアトラス"}]


@pytest.fixture
def postgresql_db():
    if os.getenv("JLTSQL_RUN_POSTGRESQL_INTEGRATION") != "1":
        pytest.skip("Set JLTSQL_RUN_POSTGRESQL_INTEGRATION=1 to run PostgreSQL tests")

    from src.database.postgresql_handler import PostgreSQLDatabase

    database = PostgreSQLDatabase(postgresql_test_config())
    schema_name = f"jlt_se_makedate_{uuid4().hex[:12]}"
    database.connect()
    try:
        database.execute(f"CREATE SCHEMA {schema_name}")
        database.execute(f"SET search_path TO {schema_name}")
        database.commit()
        yield database
    finally:
        try:
            database.rollback()
            database.execute(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
            database.commit()
        finally:
            database.disconnect()


def test_the_cancelled_race_record_lands_in_standard_postgresql(postgresql_db) -> None:
    parsed = SEParser().parse(CANCELLED_RACE_SE)
    assert parsed is not None
    postgresql_db.execute(JRAVAN_SCHEMAS["UMA_RACE"])
    postgresql_db.commit()

    stats = DataImporter(postgresql_db, use_jravan_schema=True).import_records(iter([parsed]))
    stored = postgresql_db.fetch_all("SELECT MakeDate, DataKubun, Bamei FROM UMA_RACE")

    assert stats["records_failed"] == 0
    assert stats["records_imported"] == 1
    assert stored == [{"makedate": "00000000", "datakubun": "9", "bamei": "メジロアトラス"}]


def test_standard_postgresql_date_schema_is_rejected_before_mutation(postgresql_db) -> None:
    unsafe_schema = JRAVAN_SCHEMAS["UMA_RACE"].replace(
        "MakeDate                       VARCHAR(8)          ,",
        "MakeDate                       DATE                ,",
        1,
    )
    assert unsafe_schema != JRAVAN_SCHEMAS["UMA_RACE"]
    postgresql_db.execute(unsafe_schema)
    postgresql_db.commit()

    parsed = SEParser().parse(CANCELLED_RACE_SE)
    assert parsed is not None
    with pytest.raises(SchemaMigrationError):
        DataImporter(postgresql_db, use_jravan_schema=True).import_records(iter([parsed]))

    assert postgresql_db.fetch_one("SELECT COUNT(*) AS n FROM UMA_RACE") == {"n": 0}
