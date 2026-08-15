"""Regression tests for race-day operational recovery paths."""

from types import SimpleNamespace

from scripts import raceday_verify


def test_result_completion_issue_recommends_race_fetch(monkeypatch):
    """Missing central results must direct operators to the RACE data spec."""
    counts = iter((12, 0, 0))
    monkeypatch.setattr(raceday_verify, "q", lambda *args, **kwargs: next(counts))
    monkeypatch.setattr(
        raceday_verify,
        "datetime",
        type("AfterRacing", (), {"now": staticmethod(lambda: SimpleNamespace(hour=17))}),
    )
    issues = []

    raceday_verify.check_se_results(None, "2026", "0815", issues)

    assert issues == ["Race results only 0% complete after 17:00 -- fetch RACE"]

    counts = iter((12, 12, 0))
    issues = []
    raceday_verify.check_se_results(None, "2026", "0815", issues)

    assert issues == []


def test_post_phase_uses_race_once_to_recover_missing_payouts(monkeypatch):
    """H1 is carried by RACE, so payout recovery must not request DIFN."""
    no_op_checks = (
        "check_schema",
        "check_rt_data_freshness",
        "check_race_count_by_venue",
        "check_se_results",
        "check_payout_completeness",
        "check_nl_rt_consistency",
        "check_master_data",
        "check_duplicate_race_ids",
    )
    for name in no_op_checks:
        monkeypatch.setattr(raceday_verify, name, lambda *args, **kwargs: None)
    monkeypatch.setattr(raceday_verify, "check_nl_today", lambda *args, **kwargs: {})
    monkeypatch.setattr(raceday_verify, "check_rt_today", lambda *args, **kwargs: {})

    calls = []
    monkeypatch.setattr(
        raceday_verify,
        "run_fetch",
        lambda *args: calls.append(args) or True,
    )
    args = SimpleNamespace(date="20260815", fetch=True, db="data/test.db")
    nl_checks = {
        "NL_H1  (payouts)     ": 0,
        "NL_RA  (race header) ": 12,
    }

    raceday_verify.run_phase_post(
        None, args, "2026", "0815", [], nl_checks, {}
    )

    assert calls == [("RACE", "20260815", "20260815", 1, "data/test.db")]
