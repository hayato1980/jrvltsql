#!/usr/bin/env python
"""SE MakeDate is eight ASCII digits, and nothing reads it as a date.

``fixtures/captured_records/se_cancelled_race.bin`` is real provider data, not
a synthesized record. It is one of the twelve SE records of the cancelled race
at 中山 2003-12-27 10R whose MakeDate is ``00000000``; calendar-checking that
cell stopped a full 1986-2026 backfill at its 2004 chunk. All twelve share the
same header and differ only in the per-horse span, so one record is enough.
"""

import hashlib
from pathlib import Path

import pytest

from src.database.schema import SCHEMAS
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
    assert hashlib.sha256(CANCELLED_RACE_SE).hexdigest()[:16] == "98d77576c1c4ea2a"


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


@pytest.mark.parametrize("make_date", ["20040231", "20040001", "20041332", "00000000"])
def test_make_date_is_not_read_as_a_calendar_date(make_date: str) -> None:
    """Provenance metadata nothing consumes as a date, so nothing calendar-checks it."""

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
