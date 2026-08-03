"""Unit tests for the EXPERIMENTAL (RC2-a) range-fromtime env gate.

keibaai_cloud Issue #152 / docs/specs/backfill_capacity_rc2/design.md
section 2.1. This branch is isolated (not merged to production); the test
exists to prove the required properties before any verify run is performed
on the VM:
  1. env unset -> behavior is byte-for-byte identical to the pre-existing
     start-only fromtime (no regression to production callers, who never
     set this env var), and is_experimental is False.
  2. env == "1" -> the range form "{from}000000-{to}235959" is built, and
     is_experimental is True (the single source the caller uses to decide
     whether to log the EXPERIMENTAL warning -- code-quality re-audit fix,
     see _build_fromtime's docstring).

No JV-Link COM object is needed for either case: _build_fromtime() is a
pure function of (from_date, to_date, os.environ).
"""

import os

import pytest

from src.fetcher.historical import _RANGE_FROMTIME_ENV, _build_fromtime


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Make sure no ambient env from the test runner's own shell leaks in
    # and make every test start from "unset" regardless of test order.
    monkeypatch.delenv(_RANGE_FROMTIME_ENV, raising=False)
    yield


def test_fromtime_default_env_unset_matches_current_behavior():
    assert _build_fromtime("20220101", "20221231") == ("20220101000000", False)


def test_fromtime_default_env_empty_string_matches_current_behavior():
    os.environ[_RANGE_FROMTIME_ENV] = ""
    assert _build_fromtime("20220101", "20221231") == ("20220101000000", False)


def test_fromtime_default_env_not_exactly_1_matches_current_behavior():
    # Anything other than the exact string "1" (e.g. "true", "0", "yes")
    # must NOT enable the experimental range form -- avoids surprising a
    # future caller who sets a truthy-looking-but-wrong value.
    for value in ("0", "true", "TRUE", "yes"):
        os.environ[_RANGE_FROMTIME_ENV] = value
        assert _build_fromtime("20220101", "20221231") == ("20220101000000", False)


def test_fromtime_range_form_when_env_enabled():
    os.environ[_RANGE_FROMTIME_ENV] = "1"
    assert _build_fromtime("20220101", "20221231") == (
        "20220101000000-20221231235959",
        True,
    )


def test_fromtime_range_form_uses_supplied_to_date():
    os.environ[_RANGE_FROMTIME_ENV] = "1"
    assert _build_fromtime("20100601", "20101231") == (
        "20100601000000-20101231235959",
        True,
    )
