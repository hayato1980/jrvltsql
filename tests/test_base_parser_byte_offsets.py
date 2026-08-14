#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Regression tests for BaseParser field offsets being byte offsets.

FieldDef.length is documented as "Field length in bytes", and the JV-Data
layouts are defined in bytes. Any record containing a multibyte (cp932)
character therefore has to be sliced as bytes; slicing the decoded string
shifts every following field.
"""

from typing import Dict, List, Optional

import pytest

from src.parser.av_parser import AVParser
from src.parser.base import BaseParser
from src.parser.bt_parser import BTParser
from src.parser.cc_parser import CCParser
from src.parser.ck_parser import CKParser
from src.parser.cs_parser import CSParser
from src.parser.hc_parser import HCParser
from src.parser.jc_parser import JCParser
from src.parser.rt_rc_parser import RTRCParser
from src.parser.tc_parser import TCParser
from src.parser.wc_parser import WCParser
from src.parser.we_parser import WEParser
from src.parser.wh_parser import WHParser

# Every parser that inherits BaseParser and therefore relies on its slicing.
FIELDDEF_PARSERS = [
    AVParser,
    BTParser,
    CCParser,
    CKParser,
    CSParser,
    HCParser,
    JCParser,
    RTRCParser,
    TCParser,
    WCParser,
    WEParser,
    WHParser,
]

# TC (馬体重) and WH (天候・馬場状態) are short code-only records whose plain
# string fields are all 1-2 bytes, so they cannot carry a 全角 character at all.
# Every other parser can, and gets the shifting test below.
NARROW_PARSERS = [TCParser, WHParser]
TEXT_CARRYING_PARSERS = [p for p in FIELDDEF_PARSERS if p not in NARROW_PARSERS]


def build_record(parser: BaseParser, values: Dict[str, str]) -> bytes:
    """Build a fixed-length cp932 record from field name -> value.

    Fields not present in ``values`` are left as spaces. Values are placed at
    the field's byte offset and must fit in the field's byte length.
    """
    size = max(f.start + f.length for f in parser._fields)
    buf = bytearray(b" " * size)
    for field_def in parser._fields:
        if field_def.name not in values:
            continue
        raw = values[field_def.name].encode("cp932")
        assert len(raw) <= field_def.length, (
            f"{field_def.name}: {len(raw)} bytes does not fit in {field_def.length}"
        )
        buf[field_def.start:field_def.start + len(raw)] = raw
    return bytes(buf)


def plain_str_field_names(parser: BaseParser) -> List[str]:
    """Field names that BaseParser returns verbatim (no type conversion)."""
    return [
        f.name
        for f in parser._fields
        if not f.convert_type and f.type == "str"
    ]


def char_sliced(parser: BaseParser, record: bytes) -> Dict[str, Optional[str]]:
    """Reproduce the pre-fix behaviour: slice the decoded string by character."""
    text = record.decode("cp932", errors="replace")
    result = {}
    for field_def in parser._fields:
        value = text[field_def.start:field_def.start + field_def.length].strip()
        result[field_def.name] = value or None
    return result


def test_bt_keito_fields_survive_a_full_width_record():
    """The 系統情報 case from the issue: パーソロン must not split across fields.

    KeitoId is 30 bytes and KeitoName is 36 bytes. Slicing the decoded string
    by character makes KeitoName 36 *characters* wide, so the tail of the
    record (KeitoEx, 系統説明) bleeds into it.
    """
    parser = BTParser()
    keito_ex = "トウルビヨン系で日本に最初に入った大物は"
    record = build_record(
        parser,
        {
            "RecordSpec": "BT",
            "DataKubun": "1",
            "MakeDate": "20210115",
            "HansyokuNum": "1110057602",
            "KeitoId": "010201",
            "KeitoName": "パーソロン",
            "KeitoEx": keito_ex,
            "RecordDelimiter": "\r\n",
        },
    )

    parsed = parser.parse(record)

    assert parsed["HansyokuNum"] == "1110057602"
    assert parsed["KeitoId"] == "010201"
    assert parsed["KeitoName"] == "パーソロン"
    assert parsed["KeitoEx"] == keito_ex


def test_cs_course_ex_starts_at_its_own_offset():
    """CS carries a 6800-byte 全角 description directly after 全角-free fields."""
    parser = CSParser()
    course_ex = "コース改修により直線が延長された"
    record = build_record(
        parser,
        {
            "RecordSpec": "CS",
            "DataKubun": "1",
            "MakeDate": "20260814",
            "JyoCD": "05",
            "Kyori": "2400",
            "TrackCD": "23",
            "KaishuDate": "20020101",
            "CourseEx": course_ex,
            "RecordDelimiter": "\r\n",
        },
    )

    assert parser.parse(record)["CourseEx"] == course_ex


@pytest.mark.parametrize(
    "parser_cls", TEXT_CARRYING_PARSERS, ids=[p.__name__ for p in TEXT_CARRYING_PARSERS]
)
def test_every_fielddef_parser_slices_by_bytes(parser_cls):
    """A 全角 value in one field must not shift any following field."""
    parser = parser_cls()
    head = parser._fields[0].name
    names = [n for n in plain_str_field_names(parser) if n != head]

    # A 全角 value needs a field of at least 4 bytes to sit in.
    wide_enough = [n for n in names if parser.get_field_def(n).length >= 4]
    assert wide_enough, f"{parser_cls.__name__} has no field wide enough to test"
    widest = max(wide_enough, key=lambda n: parser.get_field_def(n).length)

    # Fill every plain string field with an ASCII marker, then replace the
    # widest one with a 全角 value so that byte and character offsets diverge.
    values = {}
    for index, name in enumerate(names):
        width = min(parser.get_field_def(name).length, 3)
        values[name] = str(index % 10 ** width).zfill(width)
    values[head] = parser.record_type
    values[widest] = "全角"

    parsed = parser.parse(build_record(parser, values))

    for name, expected in values.items():
        assert parsed[name] == expected, f"{parser_cls.__name__}.{name} shifted"


@pytest.mark.parametrize(
    "parser_cls", FIELDDEF_PARSERS, ids=[p.__name__ for p in FIELDDEF_PARSERS]
)
def test_ascii_only_records_are_unchanged(parser_cls):
    """HC / WC are ASCII-only in practice and are already parsed correctly.

    For such records byte slicing and character slicing agree, so the fix must
    not move a single value — in any of the parsers.
    """
    parser = parser_cls()
    names = plain_str_field_names(parser)
    values = {}
    for index, name in enumerate(names):
        width = min(parser.get_field_def(name).length, 3)
        values[name] = str(index % 10 ** width).zfill(width)
    values[parser._fields[0].name] = parser.record_type
    record = build_record(parser, values)

    parsed = parser.parse(record)
    legacy = char_sliced(parser, record)

    for name in names:
        assert parsed[name] == legacy[name], f"{parser_cls.__name__}.{name} changed"


def test_hanro_furlong_times_stay_monotonic():
    """The 坂路調教 sanity check quoted in the issue: cumulative times increase."""
    parser = HCParser()
    record = build_record(
        parser,
        {
            "RecordSpec": "HC",
            "DataKubun": "1",
            "MakeDate": "20260814",
            "TresenKubun": "1",
            "ChokyoDate": "20260813",
            "ChokyoTime": "0630",
            "KettoNum": "2016100126",
            "HaronTime4": "0556",
            "LapTime4": "143",
            "HaronTime3": "0413",
            "LapTime3": "138",
            "HaronTime2": "0275",
            "LapTime2": "140",
            "LapTime1": "135",
            "RecordDelimiter": "\r\n",
        },
    )

    parsed = parser.parse(record)

    assert parsed["KettoNum"] == "2016100126"
    assert parsed["HaronTime2"] == "0275"
    assert parsed["HaronTime3"] == "0413"
    assert parsed["HaronTime4"] == "0556"
