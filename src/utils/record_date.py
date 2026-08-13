"""Record date extraction shared by the fetch and import layers.

Parsed records carry their date under several different field names depending
on the record type. Both the cache writer (fetch side) and the transaction
boundary decision (import side) need the same answer, so the extraction lives
here rather than in either layer.
"""

from typing import Optional


def extract_record_date(record: dict) -> Optional[str]:
    """Extract YYYYMMDD from a parsed record dict.

    Returns None for records that carry no date at all, such as the master
    data specs (horse, jockey, trainer).
    """
    year = record.get("Year") or record.get("headYear") or record.get("KaisaiNen")
    monthday = record.get("MonthDay") or record.get("headMonthDay") or record.get("KaisaiTsukihi")
    if year and monthday and len(str(year)) == 4 and len(str(monthday)) == 4:
        return str(year) + str(monthday)
    chokyo_date = record.get("ChokyoDate")
    if chokyo_date and len(str(chokyo_date)) == 8:
        return str(chokyo_date)
    return None


def extract_record_year(record: dict) -> Optional[int]:
    """Extract the calendar year from a parsed record dict.

    Returns None for records that carry no date, so callers can treat them as
    belonging to whichever year surrounds them.
    """
    record_date = extract_record_date(record)
    if record_date is None:
        return None
    try:
        return int(record_date[:4])
    except ValueError:
        return None
