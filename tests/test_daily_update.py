from datetime import datetime

import pytest

from scripts.daily_update import (
    SUBSCRIPTION_ERROR_CODES,
    UPDATE_SPECS,
    _effective_option,
    _error_code_from_exception,
    _force_incremental_options,
    _is_realtime_spec,
    _parse_ignored_error_codes,
    _select_update_specs,
)


def test_daily_update_escalates_old_difn_to_setup_option():
    old_year = datetime.now().year - 2

    assert _effective_option("DIFN", 1, f"{old_year}0101") == 4


def test_daily_update_keeps_recent_difn_incremental():
    today = datetime.now().strftime("%Y%m%d")

    assert _effective_option("DIFN", 1, today) == 1
    assert _effective_option("RACE", 2, today) == 2


def test_daily_update_selects_requested_specs():
    assert _select_update_specs("race,difn") == [("RACE", 2), ("DIFN", 1)]


def test_daily_update_rejects_unknown_specs():
    with pytest.raises(ValueError):
        _select_update_specs("RACE,NOPE")


def test_daily_update_can_force_incremental_options():
    assert _force_incremental_options([("RACE", 2), ("DIFN", 1)]) == [("RACE", 1), ("DIFN", 1)]


def test_daily_update_parses_ignored_error_codes():
    assert _parse_ignored_error_codes("-303,-2") == {-303, -2}
    assert _error_code_from_exception(Exception("JVOpen failed (code: -303)")) == -303


def test_daily_update_includes_speed_report_specs():
    specs = [spec for spec, _ in UPDATE_SPECS]

    assert "0B12" in specs
    assert "0B15" in specs


def test_daily_update_selects_speed_report_specs_case_insensitively():
    assert _select_update_specs("0b12,0b15") == [("0B12", 1), ("0B15", 1)]


def test_daily_update_includes_date_keyed_weather_and_win5_specs():
    """Daily polling includes date-keyed 0B14/0B51 but not event-keyed 0B16."""
    specs = [spec for spec, _ in UPDATE_SPECS]
    assert "0B14" in specs
    assert "0B16" not in specs
    assert "0B51" in specs


def test_daily_update_selects_event_report_specs_case_insensitively():
    assert _select_update_specs("0b14,0b51") == [("0B14", 1), ("0B51", 1)]


def test_is_realtime_spec_detects_jvrtopen_specs():
    assert _is_realtime_spec("0B12")
    assert _is_realtime_spec("0b15")
    assert not _is_realtime_spec("RACE")
    assert not _is_realtime_spec("DIFN")


def test_daily_update_includes_mining_spec():
    """MING (data-mining) must be collected so NL_DM / SE mining fields populate."""
    specs = [spec for spec, _ in UPDATE_SPECS]
    assert "MING" in specs
    assert _select_update_specs("ming") == [("MING", 1)]


def test_subscription_error_codes_cover_jvlink_unsubscribed_codes():
    """MING 等の任意契約スペックが未購読でも日次同期が止まらないよう、JV-Link の
    購読エラー(-111/-114/-115)は ignore 指定に関わらずスキップ対象とする。"""
    assert SUBSCRIPTION_ERROR_CODES == frozenset({-111, -114, -115})
    for msg, code in (
        ("JVOpen failed (code: -114)", -114),
        ("JVOpen failed (code: -111)", -111),
        ("JVOpen failed (code: -115)", -115),
    ):
        parsed = _error_code_from_exception(Exception(msg))
        assert parsed == code
        assert parsed in SUBSCRIPTION_ERROR_CODES
