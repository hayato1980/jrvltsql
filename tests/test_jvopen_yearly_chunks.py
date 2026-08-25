"""JVOpen の fromtime を暦年で刻む（keibaai_cloud#283 / ADR-0031）.

1 read の費用は JVOpen の対象ファイル数で決まる。実測（2026-08-23・RACE・option=4）:
44 ファイルなら 3.4 ms、5,096 ファイルなら 67.6 ms。だから範囲形式を使える dataspec は
暦年で刻んで JVOpen を繰り返し、1 回の対象を小さく保つ。

ここで守るのは 3 つ:
  - 境界に穴も重複も無いこと（JVOpen は「開始より大きい」「終了まで」）
  - 刻む対象を許可リストに閉じること（範囲形式で無言の 0 件になる dataspec がある）
  - option 1 の差分カーソルと option 2 の今週データ契約を変えないこと
"""

from unittest.mock import MagicMock

import pytest

from src.fetcher.base import FetcherError
from src.fetcher.historical import (
    HistoricalFetcher,
    _jvopen_fromtime,
    _jvopen_fromtimes,
)
from src.jvlink.constants import RANGE_FROMTIME_DATA_SPECS

SETUP = 4


def _starts_and_ends(fromtimes: list[str]) -> list[tuple[str, str]]:
    return [tuple(ft.split("-")) for ft in fromtimes]


class TestAllowList:
    def test_only_the_live_verified_race_spec_is_enabled(self):
        """PR evidence is provider-bound to RACE; unmeasured specs stay safe."""
        assert RANGE_FROMTIME_DATA_SPECS == frozenset({"RACE"})

    @pytest.mark.parametrize(
        "data_spec", ["TOKU", "DIFF", "DIFN", "HOSE", "HOSN", "HOYU", "COMM"]
    )
    def test_specs_that_officially_forbid_an_end_point_are_not_on_the_allow_list(
        self, data_spec
    ):
        """公式仕様 p.18 が終了時刻を禁じている種別。渡すと戻り値 -1 になる."""
        assert data_spec not in RANGE_FROMTIME_DATA_SPECS

    @pytest.mark.parametrize("data_spec", ["DIFN", "TOKU", "HOSN", "HOYU", "COMM", "BLDN"])
    def test_specs_outside_the_allow_list_open_once_without_an_end_point(self, data_spec):
        """終了時刻を受け付けない dataspec は、期間が何年でも開始のみ 1 回."""
        fromtimes = _jvopen_fromtimes(data_spec, "19860101", "20261231", SETUP)

        assert fromtimes == [_jvopen_fromtime("19860101", SETUP)]
        assert "-" not in fromtimes[0]

    def test_unmeasured_spec_falls_back_to_a_single_open(self):
        """許可リストは実測済みのものだけ。未実測の spec は刻まない."""
        assert _jvopen_fromtimes("YSCH", "19860101", "20261231", SETUP) == [
            _jvopen_fromtime("19860101", SETUP)
        ]


class TestChunkBoundaries:
    def test_one_chunk_per_calendar_year(self):
        fromtimes = _jvopen_fromtimes("RACE", "19860101", "19881231", SETUP)

        assert len(fromtimes) == 3

    def test_setup_first_chunk_starts_the_day_before_to_include_the_requested_day(self):
        """JVOpen の対象は「開始より大きい」。要求日を落とさないため前日 23:59:59."""
        first, _ = _starts_and_ends(
            _jvopen_fromtimes("RACE", "19860101", "19871231", SETUP)
        )[0]

        assert first == "19851231235959"

    def test_later_chunks_start_at_the_previous_year_end(self):
        pairs = _starts_and_ends(
            _jvopen_fromtimes("RACE", "19860101", "19881231", SETUP)
        )

        assert [start for start, _ in pairs] == [
            "19851231235959",
            "19861231235959",
            "19871231235959",
        ]

    def test_each_chunk_ends_at_its_year_end(self):
        pairs = _starts_and_ends(
            _jvopen_fromtimes("RACE", "19860101", "19881231", SETUP)
        )

        assert [end for _, end in pairs] == [
            "19861231235959",
            "19871231235959",
            "19881231235959",
        ]

    def test_adjacent_chunks_share_their_boundary_so_nothing_is_lost_or_repeated(self):
        """前の chunk は「終了まで」で含み、次の chunk は「開始より大きい」で外す."""
        pairs = _starts_and_ends(
            _jvopen_fromtimes("RACE", "19860101", "20261231", SETUP)
        )

        for (_, end), (next_start, _) in zip(pairs, pairs[1:], strict=False):  # 末尾は次が無いので短い側に合わせる
            assert end == next_start

    def test_last_chunk_ends_at_the_requested_day_not_the_year_end(self):
        pairs = _starts_and_ends(
            _jvopen_fromtimes("RACE", "20240101", "20250615", SETUP)
        )

        assert pairs[-1] == ("20241231235959", "20250615235959")

    def test_a_request_inside_one_year_is_a_single_range(self):
        assert _jvopen_fromtimes("RACE", "20220301", "20220930", SETUP) == [
            "20220228235959-20220930235959"
        ]

    def test_a_single_day_request_is_a_single_range(self):
        assert _jvopen_fromtimes("RACE", "20240229", "20240229", SETUP) == [
            "20240228235959-20240229235959"
        ]

    def test_a_leap_day_start_keeps_the_previous_calendar_day(self):
        first, _ = _starts_and_ends(
            _jvopen_fromtimes("RACE", "20240301", "20241231", SETUP)
        )[0]

        assert first == "20240229235959"

    def test_a_year_start_crossing_a_century_boundary(self):
        pairs = _starts_and_ends(
            _jvopen_fromtimes("RACE", "19991201", "20000131", SETUP)
        )

        assert pairs == [
            ("19991130235959", "19991231235959"),
            ("19991231235959", "20000131235959"),
        ]


class TestOptionContracts:
    def test_option_1_keeps_its_midnight_diff_cursor_on_the_first_chunk(self):
        """差分カーソルは触らない。setup と違って前日へずらさない."""
        first, _ = _starts_and_ends(
            _jvopen_fromtimes("RACE", "20250101", "20261231", 1)
        )[0]

        assert first == "20250101000000"

    def test_option_1_still_chunks_by_year(self):
        assert len(_jvopen_fromtimes("RACE", "20250101", "20261231", 1)) == 2

    def test_option_2_is_never_chunked(self):
        """今週データは開催サイクルが対象で、期間の概念が違う."""
        assert _jvopen_fromtimes("RACE", "19860101", "20261231", 2) == [
            _jvopen_fromtime("19860101", 2)
        ]

    @pytest.mark.parametrize("option", [3, 4])
    def test_both_setup_options_chunk(self, option):
        assert len(_jvopen_fromtimes("RACE", "20240101", "20261231", option)) == 3


class _Wrapper:
    """JVOpen/JVRead/JVClose の呼び出し順だけを記録する差し替え."""

    def __init__(
        self,
        opens: list,
        reads_per_open: list[list[tuple]],
        on_open=None,
    ):
        self._opens = list(opens)
        self._reads_per_open = [list(r) for r in reads_per_open]
        self._current_reads: list[tuple] = []
        self._on_open = on_open
        self.open_fromtimes: list[str] = []
        self.close_count = 0
        self.init_count = 0

    def jv_init(self, *args, **kwargs):
        self.init_count += 1

    def jv_open(self, data_spec, fromtime, option):
        self.open_fromtimes.append(fromtime)
        result = self._opens.pop(0)
        self._current_reads = (
            self._reads_per_open.pop(0) if self._reads_per_open else []
        )
        if self._on_open is not None:
            self._on_open(len(self.open_fromtimes))
        if isinstance(result, Exception):
            raise result
        return result

    def jv_read(self):
        return self._current_reads.pop(0)

    def jv_close(self):
        self.close_count += 1
        return 0


def _fetcher_with(wrapper) -> HistoricalFetcher:
    f = HistoricalFetcher.__new__(HistoricalFetcher)
    f.parser_factory = MagicMock()
    f.parser_factory.parse.side_effect = lambda buff: [
        {"Year": "2022", "MonthDay": "0110", "n": len(buff)}
    ]
    f.cache_manager = None
    f.show_progress = False
    f.progress_display = None
    f._service_key = None
    f._records_fetched = f._records_parsed = f._records_failed = 0
    f._files_processed = f._total_files = 0
    f._repaired_read_errors = 0
    f._start_time = 0.0
    f._jvd_self_repair_attempts = f._jvd_replay_records_remaining = 0
    f._open_records_baseline = 0
    f._recoverable_read_errors = 0
    f._jv_open_context = f._jv_open_last_file_timestamp = f._fetch_task_id = None
    f.jvlink = wrapper
    return f


DONE = (0, None, None)


def _one_record_open(ts: str = "20220110000000") -> tuple:
    """(result, read_count, download_count, last_file_timestamp)."""
    return (0, 1, 0, ts)


class TestFetchLoopsOverChunks:
    def test_opens_once_per_year_with_the_chunk_fromtimes(self):
        wrapper = _Wrapper(
            opens=[_one_record_open(), _one_record_open()],
            reads_per_open=[[(4, b"aaaa", "f1"), DONE], [(4, b"bbbb", "f2"), DONE]],
        )
        f = _fetcher_with(wrapper)

        list(f.fetch("RACE", "20240101", "20251231", option=4))

        assert wrapper.open_fromtimes == [
            "20231231235959-20241231235959",
            "20241231235959-20251231235959",
        ]

    def test_yields_records_from_every_chunk(self):
        wrapper = _Wrapper(
            opens=[_one_record_open(), _one_record_open()],
            reads_per_open=[[(4, b"aaaa", "f1"), DONE], [(6, b"bbbbbb", "f2"), DONE]],
        )
        f = _fetcher_with(wrapper)

        rows = list(f.fetch("RACE", "20240101", "20251231", option=4))

        assert [r["n"] for r in rows] == [4, 6]

    def test_statistics_accumulate_across_chunks(self):
        wrapper = _Wrapper(
            opens=[_one_record_open(), _one_record_open()],
            reads_per_open=[[(4, b"aaaa", "f1"), DONE], [(4, b"bbbb", "f2"), DONE]],
        )
        f = _fetcher_with(wrapper)

        list(f.fetch("RACE", "20240101", "20251231", option=4))

        assert f.get_statistics()["records_fetched"] == 2

    def test_a_chunk_with_no_data_does_not_stop_the_later_chunks(self):
        """空の窓は正常。-1 で fetch 全体を落とさない."""
        wrapper = _Wrapper(
            opens=[(-1, 0, 0, ""), _one_record_open()],
            reads_per_open=[[], [(4, b"bbbb", "f2"), DONE]],
        )
        f = _fetcher_with(wrapper)

        rows = list(f.fetch("RACE", "20240101", "20251231", option=4))

        assert len(rows) == 1
        assert len(wrapper.open_fromtimes) == 2

    def test_stream_is_closed_after_each_chunk(self):
        wrapper = _Wrapper(
            opens=[_one_record_open(), _one_record_open()],
            reads_per_open=[[(4, b"aaaa", "f1"), DONE], [(4, b"bbbb", "f2"), DONE]],
        )
        f = _fetcher_with(wrapper)

        list(f.fetch("RACE", "20240101", "20251231", option=4))

        assert wrapper.close_count >= 2

    def test_spec_outside_the_allow_list_opens_once_for_a_multi_year_request(self):
        wrapper = _Wrapper(
            opens=[_one_record_open()],
            reads_per_open=[[(4, b"aaaa", "f1"), DONE]],
        )
        f = _fetcher_with(wrapper)

        list(f.fetch("DIFN", "20240101", "20261231", option=4))

        assert wrapper.open_fromtimes == ["20231231235959"]


class TestChunkFailuresDoNotLeakAcrossChunks:
    def test_an_empty_window_never_marks_the_nl_cache_range_complete(self):
        """空の窓で完了マークを付けると、以後その範囲は 0 件で答え続ける."""
        wrapper = _Wrapper(
            opens=[(-1, 0, 0, ""), _one_record_open()],
            reads_per_open=[[], [(4, b"bbbb", "f2"), DONE]],
        )
        f = _fetcher_with(wrapper)
        f.cache_manager = MagicMock()
        f.cache_manager.checkpoint_nl.return_value = 0

        list(f.fetch("RACE", "20240101", "20251231", option=4))

        f.cache_manager.mark_nl_range_complete.assert_not_called()

    def test_a_fully_covered_request_still_marks_the_range_complete(self):
        """対照。空の窓が無ければ従来どおり完了マークを付ける."""
        wrapper = _Wrapper(
            opens=[_one_record_open(), _one_record_open()],
            reads_per_open=[[(4, b"aaaa", "f1"), DONE], [(4, b"bbbb", "f2"), DONE]],
        )
        f = _fetcher_with(wrapper)
        f.cache_manager = MagicMock()
        f.cache_manager.checkpoint_nl.return_value = 0

        list(f.fetch("RACE", "20240101", "20251231", option=4))

        f.cache_manager.mark_nl_range_complete.assert_called_once()

    def test_the_stream_is_closed_even_when_jvopen_itself_raises(self):
        """wrapper は開いたまま例外で返ることがある（-202）。close の義務は残る."""
        wrapper = _Wrapper(
            opens=[RuntimeError("JVOpen blew up")],
            reads_per_open=[[]],
        )
        f = _fetcher_with(wrapper)

        with pytest.raises(FetcherError):
            list(f.fetch("RACE", "20240101", "20241231", option=4))

        assert wrapper.close_count == 1

    def test_close_failure_stops_before_the_next_chunk_and_cache_completion(self):
        """A chunk is not complete until its JVClose obligation succeeds."""
        wrapper = _Wrapper(
            opens=[_one_record_open(), _one_record_open()],
            reads_per_open=[[(4, b"aaaa", "f1"), DONE], [(4, b"bbbb", "f2"), DONE]],
        )
        wrapper.jv_close = MagicMock(side_effect=RuntimeError("close failed"))
        fetcher = _fetcher_with(wrapper)
        fetcher.cache_manager = MagicMock()
        fetcher.cache_manager.checkpoint_nl.return_value = 0

        with pytest.raises(FetcherError, match="JVClose.*close failed"):
            list(fetcher.fetch("RACE", "20240101", "20251231", option=4))

        assert len(wrapper.open_fromtimes) == 1
        fetcher.cache_manager.mark_nl_range_complete.assert_not_called()

    def test_close_failure_does_not_replace_the_primary_open_error(self):
        """Close diagnostics must not hide the provider error that caused unwind."""
        primary_error = RuntimeError("JVOpen blew up")
        wrapper = _Wrapper(opens=[primary_error], reads_per_open=[[]])
        wrapper.jv_close = MagicMock(side_effect=RuntimeError("close failed"))
        fetcher = _fetcher_with(wrapper)

        with pytest.raises(FetcherError, match="JVOpen blew up") as exc_info:
            list(fetcher.fetch("RACE", "20240101", "20241231", option=4))

        assert exc_info.value.__cause__ is primary_error

    def test_an_error_code_is_not_absorbed_as_an_empty_window(self):
        """-113（終了時刻のパラメータ不正）も read_count 0 で返る。黙って進まない."""
        wrapper = _Wrapper(opens=[(-113, 0, 0, "")], reads_per_open=[[]])
        f = _fetcher_with(wrapper)

        with pytest.raises(FetcherError, match="-113"):
            list(f.fetch("RACE", "20240101", "20241231", option=4))

    def test_the_self_repair_budget_is_per_fetch_not_per_chunk(self):
        """chunk ごとに上限を配り直すと、全体では chunk 数ぶんリトライできてしまう."""
        seen = []

        def _on_open(open_number: int):
            if open_number == 1:
                fetcher._jvd_self_repair_attempts = 1
            else:
                seen.append(fetcher._jvd_self_repair_attempts)

        wrapper = _Wrapper(
            opens=[_one_record_open(), _one_record_open()],
            reads_per_open=[[(4, b"aaaa", "f1"), DONE], [(4, b"bbbb", "f2"), DONE]],
            on_open=_on_open,
        )
        fetcher = _fetcher_with(wrapper)

        list(fetcher.fetch("RACE", "20240101", "20251231", option=4))

        assert seen == [1], "2 つめの chunk でリトライ回数が 0 に戻っていない"

    def test_second_chunk_recovery_replays_only_its_own_emitted_prefix(self):
        """Earlier chunks must not inflate the reopened stream's drain count."""
        wrapper = MagicMock()
        wrapper.jv_file_delete.return_value = 0
        wrapper.jv_open.return_value = (0, 3, 1, "second-ts")
        fetcher = _fetcher_with(wrapper)
        fetcher._records_fetched = 5  # 3 from chunk 1, then 2 from chunk 2
        fetcher._open_records_baseline = 3
        fetcher._total_files = 3
        fetcher._jv_open_context = (
            "RACE",
            "20241231235959-20251231235959",
            4,
        )
        fetcher._jv_open_last_file_timestamp = "second-ts"
        fetcher._wait_for_download = MagicMock()

        fetcher._recover_historical_read_error(-402, "corrupt-second.jvd")

        assert fetcher._jvd_replay_records_remaining == 2


def test_the_headline_backfill_request_opens_once_per_year():
    """1986-2026 は 41 年。刻みの回数が年数と一致すること."""
    fromtimes = _jvopen_fromtimes("RACE", "19860101", "20261231", SETUP)

    assert len(fromtimes) == 41
    assert fromtimes[0] == "19851231235959-19861231235959"
    assert fromtimes[-1] == "20251231235959-20261231235959"
