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
import structlog

from src.fetcher.historical import _RANGE_FROMTIME_ENV, HistoricalFetcher, _build_fromtime


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


# ---------------------------------------------------------------------------
# Phase 5 follow-up (coordinator high-priority review round): near-"1" values
# must NOT enable the experimental range form -- only the EXACT string "1"
# does. This closes a class of accidental-enablement bugs (e.g. a value with
# incidental whitespace from a copy-pasted RDP session command, or a stray
# trailing newline from a config file / env-file loader) that a looser
# comparison (e.g. `.strip() == "1"` or a truthy check) would silently
# accept.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        " 1",  # leading space
        "1 ",  # trailing space
        "1\n",  # trailing newline
        "\n1",  # leading newline
        "1\t",  # trailing tab
        "01",  # zero-padded
        "1.0",  # numeric-but-not-exact
        "1.00",  # numeric-but-not-exact (coordinator follow-up 低1)
        "+1",  # explicit-sign numeric-but-not-exact (coordinator follow-up 低1)
        "true",  # already covered above, kept here for symmetry with the near-'1' set
    ],
)
def test_fromtime_near_one_values_do_not_enable_range_form(value):
    os.environ[_RANGE_FROMTIME_ENV] = value
    assert _build_fromtime("20220101", "20221231") == ("20220101000000", False)


# ---------------------------------------------------------------------------
# Phase 5 follow-up (coordinator high-priority review round, coverage 低5):
# prove the ACTUAL logger.warning() call site in HistoricalFetcher.fetch()
# (historical.py, the `if is_experimental_fromtime:` block right after
# `_build_fromtime()`) really emits the EXPERIMENTAL(RC2-a) warning when the
# env gate is enabled -- not just that `_build_fromtime()` returns the right
# tuple in isolation. Bypasses HistoricalFetcher.__init__ (which would try to
# construct a real JVLinkBridge/JVLinkWrapper, i.e. touch COM/a bridge
# executable that does not exist on this Linux CCW host) via
# object.__new__(), then hand-sets only the instance attributes fetch()
# actually reads before it reaches the warning call site. The fake
# self.jvlink.jv_open() returns (-1, 0, 0, "") -- HistoricalFetcher.fetch()
# treats that as "no data available" and does a plain `return` (a normal,
# non-exceptional generator exit), so the test never needs to touch any of
# the download/parse machinery below that point.
# ---------------------------------------------------------------------------


class _FakeJVLink:
    def __init__(self):
        self.jv_init_calls = 0
        self.jv_open_calls: list[tuple] = []

    def jv_init(self):
        self.jv_init_calls += 1

    def jv_open(self, data_spec, fromtime, option):
        self.jv_open_calls.append((data_spec, fromtime, option))
        return (-1, 0, 0, "")  # "no data available" -> fetch() returns early


def _make_bare_historical_fetcher(fake_jvlink):
    fetcher = object.__new__(HistoricalFetcher)
    fetcher.jvlink = fake_jvlink
    fetcher.cache_manager = None
    fetcher.show_progress = False
    fetcher.progress_display = None
    fetcher._service_key = None
    fetcher._records_fetched = 0
    fetcher._records_parsed = 0
    fetcher._records_failed = 0
    fetcher._recoverable_read_errors = 0
    fetcher._files_processed = 0
    fetcher._total_files = 0
    fetcher._start_time = None
    return fetcher


def test_experimental_warning_actually_logged_when_env_gate_enabled():
    os.environ[_RANGE_FROMTIME_ENV] = "1"
    fake_jvlink = _FakeJVLink()
    fetcher = _make_bare_historical_fetcher(fake_jvlink)

    with structlog.testing.capture_logs() as cap_logs:
        records = list(fetcher.fetch("RACE", "20220101", "20221231", option=1))

    assert records == []
    assert fake_jvlink.jv_init_calls == 1
    assert fake_jvlink.jv_open_calls == [
        ("RACE", "20220101000000-20221231235959", 1)
    ]
    warnings = [
        entry
        for entry in cap_logs
        if entry.get("log_level") == "warning"
        and entry.get("event") == "EXPERIMENTAL(RC2-a): range fromtime enabled"
    ]
    assert len(warnings) == 1
    assert warnings[0]["fromtime"] == "20220101000000-20221231235959"


def test_experimental_warning_not_logged_when_env_gate_disabled():
    """Converse of the above: env unset -> no EXPERIMENTAL warning at all
    (production default, no accidental logging noise)."""
    fake_jvlink = _FakeJVLink()
    fetcher = _make_bare_historical_fetcher(fake_jvlink)

    with structlog.testing.capture_logs() as cap_logs:
        list(fetcher.fetch("RACE", "20220101", "20221231", option=1))

    assert fake_jvlink.jv_open_calls == [("RACE", "20220101000000", 1)]
    warnings = [
        entry
        for entry in cap_logs
        if entry.get("log_level") == "warning"
        and "EXPERIMENTAL" in str(entry.get("event", ""))
    ]
    assert warnings == []
