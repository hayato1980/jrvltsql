"""JVOpen 読み出し開始/終了ポイント (fromtime) の公式契約テスト.

出典: JV-Link インターフェース仕様書 4.9.0.1 p.17-20。

- fromtime は「開始のみ」か「開始-終了」の2形式だけ (p.17-18)
- TOKU/DIFF/DIFN/HOSE/HOSN/HOYU/COMM は終了ポイントを指定できず、指定すると
  エラーではなく戻り値 -1（該当データなし）になる (p.18)
- option 3/4 の終了時刻が制限するのは今月の通常データ部分だけで、前月までの
  セットアップ用 tail は fromtime より大きい全件のまま (p.20)
- p.17「既知の障害について」は、対象ファイル数が多いときの JVRead 低速化の
  回避策として dataspec の個別指定と読み出し開始/終了ポイント指定を挙げる
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli.main import cli
from src.fetcher.historical import (
    HistoricalFetcher,
    _jvopen_fromtime,
    validate_jvopen_end_point,
)
from src.jvlink.bridge import JVLinkBridge
from src.jvlink.constants import (
    JVOPEN_END_POINT_FORBIDDEN_DATA_SPECS,
    format_jvopen_fromtime,
    split_jvopen_fromtime,
    supports_jvopen_end_point,
    validate_jvopen_fromtime,
)
from src.jvlink.wrapper import JVLinkWrapper

# p.18 が終了ポイント指定を禁じる ID のうち、jrvltsql が現行仕様として扱う ID。
# DIFF/HOSE は旧仕様として別途拒否されるため、ここでは現行 ID だけを回す。
CURRENT_END_POINT_FORBIDDEN = ("TOKU", "DIFN", "HOSN", "HOYU", "COMM")


def _wrapper():
    wrapper = JVLinkWrapper.__new__(JVLinkWrapper)
    wrapper.sid = "TEST"
    wrapper._jvlink = MagicMock()
    wrapper._jvlink.JVOpen.return_value = (0, 100, 0, "20241231235959")
    wrapper._is_open = False
    wrapper._com_initialized = False
    return wrapper


def _bridge():
    bridge = JVLinkBridge.__new__(JVLinkBridge)
    bridge.sid = "TEST"
    bridge._send_command = MagicMock(
        return_value={
            "status": "ok",
            "code": 0,
            "readcount": 100,
            "downloadcount": 5,
            "lastfiletimestamp": "20241231235959",
        }
    )
    bridge._is_open = False
    return bridge


def _historical_fetcher(jvlink):
    with (
        patch("src.jvlink.bridge.find_bridge_executable", return_value=None),
        patch("src.fetcher.base.JVLinkWrapper", return_value=jvlink),
    ):
        return HistoricalFetcher(sid="TEST", show_progress=False)


# --- fromtime の形式そのもの (p.17-18) --------------------------------------


class TestOfficialFromtimeForms:
    def test_start_only_form_is_returned_verbatim(self):
        assert format_jvopen_fromtime("20240101000000") == "20240101000000"

    def test_start_end_form_is_joined_by_a_half_width_hyphen(self):
        assert (
            format_jvopen_fromtime("20240101000000", "20241231235959")
            == "20240101000000-20241231235959"
        )

    def test_a_date_only_read_point_completes_to_that_days_last_second(self):
        # 「開始時刻より大きくかつ終了時刻まで」なので、その日を丸ごと含めるには
        # 終了ポイントを 23:59:59 まで伸ばす。
        assert (
            format_jvopen_fromtime("20240101", "20241231")
            == "20240101235959-20241231235959"
        )

    def test_split_returns_the_start_and_optional_end_point(self):
        assert split_jvopen_fromtime("20240101000000") == ("20240101000000", None)
        assert split_jvopen_fromtime("20240101000000-20241231235959") == (
            "20240101000000",
            "20241231235959",
        )

    @pytest.mark.parametrize(
        "fromtime",
        [
            "2024010100000",  # 13桁
            "202401010000000",  # 15桁
            "2024-01-01T00:00:00",  # 区切り文字入り
            "20240101000000-",  # 終了ポイント欠落
            "20240101000000-20241231235959-20250101000000",  # ハイフン過多
            "20241332000000",  # 実在しない暦日
            "20240101000000-20240101000000",  # 空範囲 (開始 >= 終了)
            "20241231235959-20240101000000",  # 逆転
            20240101000000,  # 文字列ではない
        ],
    )
    def test_unofficial_forms_are_rejected(self, fromtime):
        with pytest.raises(ValueError):
            validate_jvopen_fromtime(fromtime, "RACE")


class TestEndPointForbiddenSpecs:
    def test_the_forbidden_set_is_the_official_p18_list(self):
        assert set(JVOPEN_END_POINT_FORBIDDEN_DATA_SPECS) == {
            "TOKU",
            "DIFF",
            "DIFN",
            "HOSE",
            "HOSN",
            "HOYU",
            "COMM",
        }

    @pytest.mark.parametrize("data_spec", CURRENT_END_POINT_FORBIDDEN)
    def test_forbidden_specs_do_not_support_an_end_point(self, data_spec):
        assert supports_jvopen_end_point(data_spec) is False

    @pytest.mark.parametrize("data_spec", ["RACE", "BLDN", "SLOP", "WOOD", "YSCH"])
    def test_other_current_specs_support_an_end_point(self, data_spec):
        assert supports_jvopen_end_point(data_spec) is True

    def test_one_forbidden_component_forbids_the_whole_concatenated_spec(self):
        # 連結指定は「全体で1リクエスト」。1つでも禁止 ID が混ざれば -1 になる。
        assert supports_jvopen_end_point("RACEDIFN") is False

    @pytest.mark.parametrize("data_spec", CURRENT_END_POINT_FORBIDDEN)
    def test_an_end_point_on_a_forbidden_spec_is_rejected(self, data_spec):
        with pytest.raises(ValueError) as excinfo:
            validate_jvopen_fromtime(
                "20240101000000-20241231235959", data_spec
            )

        # -1 は「エラー」ではなく「該当データなし」として返るため、なぜ空になるかを
        # 呼び出し側が読めるようにしておく。
        assert "-1" in str(excinfo.value)


# --- 送信層のガード ---------------------------------------------------------


class TestTransportRejectsBeforeTheCall:
    def test_com_receives_the_official_start_end_form_for_race(self):
        wrapper = _wrapper()

        wrapper.jv_open("RACE", "20240101000000-20241231235959", option=1)

        wrapper._jvlink.JVOpen.assert_called_once_with(
            "RACE", "20240101000000-20241231235959", 1, 0, 0, ""
        )

    @pytest.mark.parametrize("data_spec", CURRENT_END_POINT_FORBIDDEN)
    def test_com_is_never_called_with_a_forbidden_end_point(self, data_spec):
        wrapper = _wrapper()

        with pytest.raises(ValueError):
            wrapper.jv_open(
                data_spec, "20240101000000-20241231235959", option=1
            )

        wrapper._jvlink.JVOpen.assert_not_called()
        assert wrapper.is_open() is False

    def test_com_is_never_called_with_an_unofficial_fromtime(self):
        wrapper = _wrapper()

        with pytest.raises(ValueError):
            wrapper.jv_open("RACE", "20240101-20241231", option=1)

        wrapper._jvlink.JVOpen.assert_not_called()

    def test_bridge_transmits_the_official_start_end_form_for_race(self):
        bridge = _bridge()

        bridge.jv_open("RACE", "20240101000000-20241231235959", option=1)

        assert (
            bridge._send_command.call_args.args[0]["fromtime"]
            == "20240101000000-20241231235959"
        )

    @pytest.mark.parametrize("data_spec", CURRENT_END_POINT_FORBIDDEN)
    def test_bridge_never_transmits_a_forbidden_end_point(self, data_spec):
        bridge = _bridge()

        with pytest.raises(ValueError):
            bridge.jv_open(data_spec, "20240101000000-20241231235959", option=1)

        bridge._send_command.assert_not_called()
        assert bridge.is_open() is False


# --- fetcher が組み立てる fromtime ------------------------------------------


class TestFetcherBuildsTheRequestedReadPoints:
    def test_option_1_stays_start_only_without_an_explicit_end_point(self):
        # --to は開催日のclient-side filterであって提供時刻ではないため、
        # 終了ポイントを勝手に作らない（後日提供される成績を落とさない）。
        assert _jvopen_fromtime("20240101", 1) == "20240101000000"

    def test_option_1_uses_the_official_start_end_form_when_asked(self):
        assert (
            _jvopen_fromtime("20240101", 1, "20241231235959")
            == "20240101000000-20241231235959"
        )

    def test_option_2_can_also_carry_an_end_point(self):
        assert (
            _jvopen_fromtime("20240101", 2, "20240108")
            == "20240101000000-20240108235959"
        )

    @pytest.mark.parametrize("option", [3, 4])
    def test_setup_refuses_an_end_point(self, option):
        # p.20: 前月までのセットアップ用データは fromtime より大きい全件が対象で、
        # 終了時刻が制限するのは今月の通常データ部分だけ。
        with pytest.raises(ValueError):
            _jvopen_fromtime("20240101", option, "20241231235959")

    @pytest.mark.parametrize("option", [3, 4])
    def test_validate_names_the_option_reason(self, option):
        with pytest.raises(ValueError) as excinfo:
            validate_jvopen_end_point("RACE", option, "20241231")

        assert "p.20" in str(excinfo.value)

    def test_jvopen_receives_the_bounded_fromtime(self):
        jvlink = MagicMock()
        jvlink.jv_open.return_value = (-1, 0, 0, "")
        fetcher = _historical_fetcher(jvlink)

        assert (
            list(
                fetcher.fetch(
                    "RACE", "20240101", "20241231", 1, fromtime_end="20241231"
                )
            )
            == []
        )

        jvlink.jv_open.assert_called_once_with(
            "RACE", "20240101000000-20241231235959", 1
        )

    def test_a_forbidden_spec_fails_before_any_jvlink_call(self):
        jvlink = MagicMock()
        fetcher = _historical_fetcher(jvlink)

        with pytest.raises(ValueError):
            list(
                fetcher.fetch(
                    "DIFN", "20240101", "20241231", 1, fromtime_end="20241231"
                )
            )

        jvlink.jv_init.assert_not_called()
        jvlink.jv_open.assert_not_called()

    def test_a_bounded_fetch_never_marks_an_nl_cache_range_complete(self):
        # 終了ポイントは提供時刻の上限であって開催日の上限ではない。要求した
        # 日付範囲を満たしたとは言えないので、完全キャッシュを主張しない。
        jvlink = MagicMock()
        jvlink.jv_open.return_value = (-1, 0, 0, "")
        cache = MagicMock()
        cache.has_nl_range.return_value = False
        fetcher = _historical_fetcher(jvlink)

        assert (
            list(
                fetcher.fetch_with_cache(
                    cache,
                    "RACE",
                    "20240101",
                    "20241231",
                    1,
                    fromtime_end="20241231",
                )
            )
            == []
        )

        cache.mark_nl_range_complete.assert_not_called()
        cache.write_nl_record.assert_not_called()
        assert fetcher.cache_manager is None

    def test_an_unbounded_fetch_keeps_writing_through_to_the_cache(self):
        jvlink = MagicMock()
        jvlink.jv_open.return_value = (-1, 0, 0, "")
        cache = MagicMock()
        cache.has_nl_range.return_value = False
        fetcher = _historical_fetcher(jvlink)

        list(fetcher.fetch_with_cache(cache, "RACE", "20240101", "20241231", 1))

        jvlink.jv_open.assert_called_once_with("RACE", "20240101000000", 1)


# --- CLI ---------------------------------------------------------------------

MINIMAL_CLI_CONFIG = """\
jvlink: {}
database:
  type: sqlite
databases:
  sqlite:
    enabled: true
    path: test.db
auto_update_check: false
"""


_EMPTY_STATS = {
    "records_fetched": 0,
    "records_parsed": 0,
    "records_imported": 0,
    "records_failed": 0,
}


def _invoke_cli_with_config(args):
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("config.yaml").write_text(MINIMAL_CLI_CONFIG, encoding="utf-8")
        return runner.invoke(cli, ["--config", "config.yaml", *args])


class TestFetchCommandReadEndPoint:
    def test_the_end_point_reaches_the_batch_processor(self):
        with patch("src.importer.batch.BatchProcessor") as processor_class:
            process = processor_class.return_value.process_date_range
            process.return_value = _EMPTY_STATS
            result = _invoke_cli_with_config(
                [
                    "fetch",
                    "--from", "20240101",
                    "--to", "20241231",
                    "--spec", "RACE",
                    "--db", "sqlite",
                    "--fromtime-end", "20241231",
                ]
            )

        assert result.exit_code == 0, result.output
        assert process.call_args.kwargs["fromtime_end"] == "20241231235959"

    @pytest.mark.parametrize("data_spec", CURRENT_END_POINT_FORBIDDEN)
    def test_a_forbidden_spec_is_reported_before_the_database_is_touched(
        self, data_spec
    ):
        with patch("src.importer.batch.BatchProcessor") as process:
            result = _invoke_cli_with_config(
                [
                    "fetch",
                    "--from", "20240101",
                    "--to", "20241231",
                    "--spec", data_spec,
                    "--db", "sqlite",
                    "--fromtime-end", "20241231",
                ]
            )

        assert result.exit_code != 0
        assert data_spec in result.output
        process.assert_not_called()

    @pytest.mark.parametrize("option", ["3", "4"])
    def test_setup_options_reject_an_end_point(self, option):
        with patch("src.importer.batch.BatchProcessor") as process:
            result = _invoke_cli_with_config(
                [
                    "fetch",
                    "--from", "20240101",
                    "--to", "20241231",
                    "--spec", "RACE",
                    "--option", option,
                    "--db", "sqlite",
                    "--fromtime-end", "20241231",
                ]
            )

        assert result.exit_code != 0
        process.assert_not_called()

    def test_an_unbounded_fetch_points_at_the_known_slowdown_workaround(self):
        with patch("src.importer.batch.BatchProcessor") as processor_class:
            process = processor_class.return_value.process_date_range
            process.return_value = _EMPTY_STATS
            result = _invoke_cli_with_config(
                [
                    "fetch",
                    "--from", "20240101",
                    "--to", "20241231",
                    "--spec", "RACE",
                    "--db", "sqlite",
                ]
            )

        assert result.exit_code == 0, result.output
        assert "--fromtime-end" in result.output
        assert process.call_args.kwargs["fromtime_end"] is None
