"""`--to` は JVOpen の fromtime に届く終了境界であること（クライアント側フィルタだけではない）.

開始のみの fromtime だと option=3/4 のセットアップは指定時刻から実行当日までを
全量ダウンロードする。範囲形式（`YYYYMMDDhhmmss-YYYYMMDDhhmmss`）はダウンロード量
そのものを窓に閉じる。

ただしマスタ系 dataspec は範囲形式だと **エラーを返さず 0 件** を返す。したがって
ここでの判定は「例外が飛ばないこと」ではなく **件数** で行う。エラーにならない失敗は、
例外を見ているテストからは成功と区別がつかない。
"""

from unittest.mock import MagicMock

import pytest

from src.fetcher.historical import HistoricalFetcher
from src.jvlink.constants import build_jvopen_fromtime, supports_range_fromtime

JV_READ_COMPLETE = 0
RANGE_2022 = "20220101000000-20221231235959"
START_ONLY_2022 = "20220101000000"


# --------------------------------------------------------------------------
# fromtime の組み立て
# --------------------------------------------------------------------------


@pytest.mark.parametrize("data_spec", ["RACE", "SLOP", "WOOD"])
def test_measured_specs_get_the_range_form(data_spec):
    """範囲形式で年の窓に絞れることを実測した dataspec は終了境界を受け取る."""
    assert build_jvopen_fromtime(data_spec, "20220101", "20221231", 4) == RANGE_2022


@pytest.mark.parametrize("data_spec", ["DIFN", "BLDN"])
def test_master_specs_fall_back_to_start_only(data_spec):
    """マスタ系は開始のみへ自動フォールバックする（呼び出し側は指定しない）."""
    assert build_jvopen_fromtime(data_spec, "20220101", "20221231", 4) == START_ONLY_2022


@pytest.mark.parametrize("data_spec", ["YSCH", "HOYU", "HOSN", "COMM", "MING", "SNPN", "TOKU"])
def test_unmeasured_specs_fall_back_to_start_only(data_spec):
    """未実測の dataspec も開始のみ側へ倒す.

    許可リストであって拒否リストではない。開始のみは同じ窓の範囲形式の上位集合
    なので、判断を誤ったときの代償はダウンロード量であって取りこぼしではない。
    """
    assert build_jvopen_fromtime(data_spec, "20220101", "20221231", 4) == START_ONLY_2022


def test_option2_never_gets_an_end_bound():
    """option=2 の fromtime は開催サイクル内の連続性管理用で、過去の窓を選ばない."""
    assert build_jvopen_fromtime("RACE", "20220101", "20221231", 2) == START_ONLY_2022
    assert supports_range_fromtime("RACE", 2) is False


def test_missing_to_date_gives_the_start_only_form():
    assert build_jvopen_fromtime("RACE", "20220101", None, 4) == START_ONLY_2022


def test_spec_matching_is_case_insensitive():
    """CacheManager が spec.upper() で引くのに合わせ、小文字でも同じ扱いにする."""
    assert build_jvopen_fromtime("race", "20220101", "20221231", 4) == RANGE_2022


def test_end_bound_covers_the_whole_of_to_date():
    """終端は to_date の 23:59:59。日付の途中で切ると当日分を落とす."""
    assert build_jvopen_fromtime("RACE", "20220101", "20220101", 4) == (
        "20220101000000-20220101235959"
    )


# --------------------------------------------------------------------------
# fetch() が実際に JVOpen へ渡すもの
# --------------------------------------------------------------------------


def _fetcher(jv_open_impl) -> HistoricalFetcher:
    """JV-Link を持たない HistoricalFetcher を組み立てる."""
    f = HistoricalFetcher.__new__(HistoricalFetcher)
    f.parser_factory = MagicMock()
    f.parser_factory.parse.return_value = [{"Year": "2022", "MonthDay": "0110"}]
    f.cache_manager = None
    f.show_progress = False
    f.progress_display = None
    f._service_key = None
    f._records_fetched = f._records_parsed = f._records_failed = 0
    f._files_processed = f._total_files = 0
    f._start_time = 0.0
    f._jvd_self_repair_attempts = f._jvd_replay_records_remaining = 0
    f._recoverable_read_errors = 0
    f._jv_open_context = f._jv_open_last_file_timestamp = f._fetch_task_id = None

    f.jvlink = MagicMock()
    f.jvlink.jv_init.return_value = None
    f.jvlink.jv_open.side_effect = jv_open_impl
    f.jvlink.jv_read.side_effect = [(100, b"X" * 100, "f1"), (JV_READ_COMPLETE, None, None)]
    return f


def _always_one_record(data_spec, fromtime, option):
    return (0, 1, 0, "20220110000000")


def _fromtime_passed_to_jvopen(data_spec: str, option: int = 4) -> str:
    f = _fetcher(_always_one_record)
    list(f.fetch(data_spec, "20220101", "20221231", option=option))
    return f.jvlink.jv_open.call_args.args[1]


def test_race_setup_opens_with_the_year_window():
    assert _fromtime_passed_to_jvopen("RACE") == RANGE_2022


def test_master_setup_opens_with_the_start_only_form():
    assert _fromtime_passed_to_jvopen("DIFN") == START_ONLY_2022


def test_the_replay_context_carries_the_window():
    """JVD 自己修復の再オープンが窓を落とさないこと.

    再オープンは `_jv_open_context` を使い回す（`fetch` 内で組んだ fromtime を
    そのまま持つ）。ここが開始のみに戻ると、修復のたびに実行当日までの全量へ
    広がってしまう。context は fetch 終了時に破棄されるので、JVOpen が呼ばれた
    瞬間の値を捕まえる。
    """
    seen = []

    def capture(data_spec, fromtime, option):
        seen.append(f._jv_open_context)
        return _always_one_record(data_spec, fromtime, option)

    f = _fetcher(capture)
    list(f.fetch("RACE", "20220101", "20221231", option=4))

    assert seen == [("RACE", RANGE_2022, 4)]


# --------------------------------------------------------------------------
# 「エラーではなく 0 件」という失敗の仕方（#183 の実測）
# --------------------------------------------------------------------------


def _jv_link_that_starves_master_ranges(data_spec, fromtime, option):
    """マスタ系に範囲形式を渡すと、エラーを返さず「該当データ無し」を返す JV-Link.

    実測（2026-08-12・option=4・有人 RDP）の挙動をそのまま写した fake。
    2022 年窓・2025 年窓とも 0 件、同じ窓を開始のみで開くと 221,917 件。
    """
    is_master = data_spec.upper() in {"DIFN", "BLDN"}
    if is_master and "-" in fromtime:
        return (-1, 0, 0, "")  # JV_RT_ERROR: 該当データ無し
    return (0, 1, 0, "20220110000000")


@pytest.mark.parametrize("data_spec", ["DIFN", "BLDN"])
def test_master_fetch_is_not_silently_empty(data_spec):
    """判定はエラーの有無ではなく件数で行う（無言の 0 件が本件の失敗の形）."""
    f = _fetcher(_jv_link_that_starves_master_ranges)

    records = list(f.fetch(data_spec, "20220101", "20221231", option=4))

    assert records, (
        f"{data_spec} が 0 件で返った。範囲形式の fromtime で JVOpen した可能性が高い "
        f"(fromtime={f.jvlink.jv_open.call_args.args[1]})。JV-Link はこの場合"
        f"エラーを返さないので、例外の有無では検出できない。"
    )


def test_race_fetch_still_returns_records_under_the_range_form():
    """陽性対照: 同じ fake で RACE は範囲形式のまま件数が返ること."""
    f = _fetcher(_jv_link_that_starves_master_ranges)

    records = list(f.fetch("RACE", "20220101", "20221231", option=4))

    assert records
    assert f.jvlink.jv_open.call_args.args[1] == RANGE_2022
