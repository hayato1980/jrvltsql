"""`realtime speed-report` accepts only date-keyed specs and runs one pass."""

import pytest

from src.cli.main import cli
from src.jvlink.constants import (
    JVRTOPEN_DATE_KEYED_SPECS,
    is_date_keyed_spec,
)
from tests.cli_test_support import CliRunner


CONFIG_YAML = """
jvlink: {}
database:
  type: "sqlite"
databases:
  sqlite:
    enabled: true
    path: "./data/keiba.db"
"""


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(CONFIG_YAML, encoding="utf-8")
    return str(path)


@pytest.fixture
def runner():
    return CliRunner()


def _invoke(runner, config_path, *args):
    return runner.invoke(cli, ["--config", config_path, "realtime", "speed-report", *args])


def _unwrapped(output: str) -> str:
    """Join the console's soft-wrapped lines so messages can be matched whole."""
    return " ".join(output.split())


# ── which specs this command is for ──────────────────────────────────────────


def test_date_keyed_specs_cover_every_speed_report_spec_except_the_event_keyed_one():
    """0B16 is opened with a JVWatchEvent key, so a date key cannot open it."""
    assert set(JVRTOPEN_DATE_KEYED_SPECS) == {
        "0B11",
        "0B12",
        "0B13",
        "0B14",
        "0B15",
        "0B17",
        "0B51",
    }
    assert not is_date_keyed_spec("0B16")


def test_date_keyed_predicate_rejects_race_keyed_odds_specs():
    for code in ("0B20", "0B30", "0B36", "0B41", "0B42"):
        assert not is_date_keyed_spec(code)


def test_speed_report_points_odds_specs_at_the_time_series_command(runner, config_path):
    result = _invoke(runner, config_path, "--spec", "0B30", "--from-date", "20260912")

    assert result.exit_code == 2
    assert "realtime timeseries" in _unwrapped(result.output)


def test_speed_report_rejects_the_event_keyed_spec(runner, config_path):
    result = _invoke(runner, config_path, "--spec", "0B16", "--from-date", "20260912")

    assert result.exit_code == 2
    assert "0B16" in _unwrapped(result.output)


def test_speed_report_rejects_one_bad_spec_among_good_ones(runner, config_path):
    result = _invoke(runner, config_path, "--spec", "0B11,0B30", "--from-date", "20260912")

    assert result.exit_code == 2


def test_speed_report_requires_a_spec(runner, config_path):
    result = _invoke(runner, config_path, "--from-date", "20260912")

    assert result.exit_code != 0
    assert "--spec" in _unwrapped(result.output)


# ── date window ──────────────────────────────────────────────────────────────


def test_speed_report_rejects_a_malformed_date(runner, config_path):
    result = _invoke(runner, config_path, "--spec", "0B11", "--from-date", "2026-09-12")

    assert result.exit_code == 2
    assert "YYYYMMDD" in _unwrapped(result.output)


def test_speed_report_rejects_a_reversed_window(runner, config_path):
    result = _invoke(
        runner,
        config_path,
        "--spec",
        "0B11",
        "--from-date",
        "20260913",
        "--to-date",
        "20260912",
    )

    assert result.exit_code == 2


# ── one pass, one JV-Link session ────────────────────────────────────────────


class _RecordingPass:
    """Stand in for the drain loop and record how it was called."""

    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "records_fetched": 2,
            "records_parsed": 2,
            "records_imported": 2,
            "records_failed": 0,
        }


class _FakeJVLink:
    def __init__(self):
        self.init_count = 0
        self.close_count = 0

    def jv_init(self):
        self.init_count += 1
        return 0

    def jv_close(self):
        self.close_count += 1
        return 0


class _FakeDatabase:
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


@pytest.fixture
def stubbed_pass(monkeypatch):
    """Replace the database, the JV-Link session and the drain loop."""
    recorded = _RecordingPass()
    jvlink = _FakeJVLink()

    monkeypatch.setattr(
        "src.realtime.speed_report.sync_date_keyed_spec", recorded, raising=True
    )
    monkeypatch.setattr(
        "src.database.create_database_from_config",
        lambda *_args, **_kwargs: _FakeDatabase(),
        raising=True,
    )

    class _FakeFetcher:
        def __init__(self, sid="JLTSQL"):
            self.jvlink = jvlink

    monkeypatch.setattr("src.fetcher.realtime.RealtimeFetcher", _FakeFetcher, raising=True)
    return recorded, jvlink


def test_speed_report_runs_one_pass_per_spec_in_one_jvlink_session(
    runner, config_path, stubbed_pass
):
    recorded, jvlink = stubbed_pass

    result = _invoke(
        runner, config_path, "--spec", "0B11,0B14", "--from-date", "20260912"
    )

    assert result.exit_code == 0, result.output
    assert [call["spec"] for call in recorded.calls] == ["0B11", "0B14"]
    # One session for the whole run, not one per spec.
    assert jvlink.init_count == 1
    assert all(call["jvlink"] is jvlink for call in recorded.calls)


def test_speed_report_establishes_the_schema_once(runner, config_path, stubbed_pass):
    recorded, _jvlink = stubbed_pass

    _invoke(runner, config_path, "--spec", "0B11,0B14,0B51", "--from-date", "20260912")

    assert [call["ensure_tables"] for call in recorded.calls] == [True, False, False]


def test_speed_report_defaults_the_window_to_a_single_day(
    runner, config_path, stubbed_pass
):
    recorded, _jvlink = stubbed_pass

    _invoke(runner, config_path, "--spec", "0B11", "--from-date", "20260912")

    assert recorded.calls[0]["from_date"] == "20260912"
    assert recorded.calls[0]["to_date"] == "20260912"


def test_speed_report_closes_the_session_when_a_pass_fails(
    runner, config_path, stubbed_pass, monkeypatch
):
    _recorded, jvlink = stubbed_pass

    def failing(**_kwargs):
        raise RuntimeError("0B14 20260912 JVRTOpen failed: -202")

    monkeypatch.setattr(
        "src.realtime.speed_report.sync_date_keyed_spec", failing, raising=True
    )

    result = _invoke(runner, config_path, "--spec", "0B14", "--from-date", "20260912")

    assert result.exit_code == 1
    assert jvlink.close_count == 1
