#!/usr/bin/env python
"""2023-08 に廃止された旧 dataspec を受け付けないことのテスト。

旧名（DIFF / BLOD / SNAP / HOSE / TCOV / RCOV）と新名（DIFN / BLDN / SNPN /
HOSN / TCVN / RCVN）は別名ではない。2023-08 の JV-Data 仕様変更で桁数が変わって
おり（繁殖登録番号 8→10 / 生産者コード 6→8 / 生産者名 70→72）、旧名を要求すると
現行パーサが解釈できない別仕様のバイト列が降ってくる。旧仕様のデータは変換せず
新 dataspec で取り直す運用に決めたため、旧名は入口で拒否する。

RACE は 2023-08 の仕様変更の対象外なので、拒否対象に含めない。
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from src.cli.main import cli
from src.fetcher.historical import HistoricalFetcher
from src.jvlink.constants import (
    JV_RT_ERROR,
    JVOPEN_VALID_COMBINATIONS,
    RETIRED_DATA_SPECS,
    is_retired_data_spec,
    is_valid_jvopen_combination,
    retired_data_spec_message,
)

RETIRED = ("DIFF", "BLOD", "SNAP", "HOSE", "TCOV", "RCOV")
REPLACEMENTS = ("DIFN", "BLDN", "SNPN", "HOSN", "TCVN", "RCVN")


class TestRetiredDataSpecTable:
    def test_retired_specs_map_to_their_replacements(self):
        assert RETIRED_DATA_SPECS == {
            "DIFF": "DIFN",
            "BLOD": "BLDN",
            "SNAP": "SNPN",
            "HOSE": "HOSN",
            "TCOV": "TCVN",
            "RCOV": "RCVN",
        }

    @pytest.mark.parametrize("data_spec", RETIRED)
    def test_retired_specs_are_recognized(self, data_spec):
        assert is_retired_data_spec(data_spec) is True

    @pytest.mark.parametrize("data_spec", REPLACEMENTS + ("RACE", "TOKU", "YSCH"))
    def test_current_specs_are_not_retired(self, data_spec):
        assert is_retired_data_spec(data_spec) is False

    def test_race_is_not_retired(self):
        # RACE は 2023-08 の桁数変更の対象外。拒否は 6 つに限る。
        assert "RACE" not in RETIRED_DATA_SPECS
        assert len(RETIRED_DATA_SPECS) == 6

    @pytest.mark.parametrize("data_spec", ("diff", "Diff", "bLoD", "snap", "hose"))
    def test_lowercase_spellings_are_also_retired(self, data_spec):
        # CacheManager は spec.upper() でディレクトリを引くので、小文字で渡しても
        # 同じ nl/DIFF/ を読める。大小を区別すると拒否をすり抜けてしまう。
        assert is_retired_data_spec(data_spec) is True
        assert RETIRED_DATA_SPECS[data_spec.upper()] in retired_data_spec_message(data_spec)


class TestJVOpenCombinations:
    @pytest.mark.parametrize("option", sorted(JVOPEN_VALID_COMBINATIONS))
    def test_no_option_accepts_a_retired_spec(self, option):
        accepted = set(JVOPEN_VALID_COMBINATIONS[option])
        assert accepted.isdisjoint(RETIRED_DATA_SPECS)

    @pytest.mark.parametrize("data_spec", RETIRED)
    @pytest.mark.parametrize("option", (1, 2, 3, 4))
    def test_is_valid_jvopen_combination_rejects_retired(self, data_spec, option):
        assert is_valid_jvopen_combination(data_spec, option) is False

    @pytest.mark.parametrize("data_spec", ("DIFN", "BLDN", "SNPN", "HOSN"))
    @pytest.mark.parametrize("option", (1, 3, 4))
    def test_replacements_remain_valid_for_accumulated_options(self, data_spec, option):
        assert is_valid_jvopen_combination(data_spec, option) is True

    @pytest.mark.parametrize("data_spec", ("TCVN", "RCVN"))
    def test_change_specs_remain_valid_for_option_2(self, data_spec):
        assert is_valid_jvopen_combination(data_spec, 2) is True

    @pytest.mark.parametrize("option", (1, 2, 3, 4))
    def test_race_still_passes_on_every_option(self, option):
        assert is_valid_jvopen_combination("RACE", option) is True


class TestRejectionMessage:
    @pytest.mark.parametrize("data_spec,replacement", list(zip(RETIRED, REPLACEMENTS, strict=True)))
    def test_message_names_the_replacement_and_when_it_changed(self, data_spec, replacement):
        message = retired_data_spec_message(data_spec)
        assert data_spec in message
        assert replacement in message
        assert "2023-08" in message

    def test_message_rejects_non_retired_spec(self):
        with pytest.raises(ValueError):
            retired_data_spec_message("RACE")

    def test_constants_no_longer_claim_the_names_are_aliases(self):
        # 受け入れ条件: constants.py から「別名 / equivalent」という宣言が消えている
        # こと。旧名は新名の別表記ではないので、そう読める記述を残さない。
        source = (Path(__file__).resolve().parents[1] / "src/jvlink/constants.py").read_text(
            encoding="utf-8"
        )
        for claim in (
            "are aliases",
            "are equivalent",
            "(DIFF の別名)",
            "(BLOD の別名)",
            "(HOSE の別名)",
        ):
            assert claim not in source, f"constants.py still claims {claim!r}"


class TestFetcherRejectsBeforeReachingJVLink:
    """取得器は生成器なので、例外は最初の反復で出る。

    JVOpen に到達しないことが要点で、送出のタイミングは問わない。
    """

    def _fetcher(self):
        # JVLinkWrapper は Windows COM を掴むので、__init__ を通さずに組み立てる
        # (tests/test_jvd_self_repair.py と同じ方式)。
        fetcher = HistoricalFetcher.__new__(HistoricalFetcher)
        fetcher.jvlink = MagicMock()
        fetcher.jvlink.jv_init.return_value = 0
        fetcher.jvlink.jv_open.return_value = (JV_RT_ERROR, 0, 0, "")  # -1 = 該当データ無し
        fetcher.parser_factory = MagicMock()
        fetcher.show_progress = False
        fetcher.progress_display = None
        fetcher.cache_manager = None
        fetcher._fetch_task_id = None
        fetcher._jvd_self_repair_attempts = 0
        fetcher._jvd_replay_records_remaining = 0
        fetcher._jv_open_context = None
        fetcher._jv_open_last_file_timestamp = None
        return fetcher

    @pytest.mark.parametrize("data_spec", RETIRED)
    def test_fetch_never_reaches_jvopen(self, data_spec):
        fetcher = self._fetcher()

        with pytest.raises(ValueError) as excinfo:
            list(fetcher.fetch(data_spec, "20240101", "20241231", option=1))

        assert data_spec in str(excinfo.value)
        assert RETIRED_DATA_SPECS[data_spec] in str(excinfo.value)
        fetcher.jvlink.jv_init.assert_not_called()
        fetcher.jvlink.jv_open.assert_not_called()

    def test_fetch_still_opens_the_stream_for_the_replacement(self):
        fetcher = self._fetcher()

        assert list(fetcher.fetch("DIFN", "20240101", "20241231")) == []

        fetcher.jvlink.jv_open.assert_called_once()
        assert fetcher.jvlink.jv_open.call_args.args[0] == "DIFN"

    @pytest.mark.parametrize("data_spec", RETIRED)
    def test_fetch_with_cache_rejects_before_reading_the_cache(self, data_spec):
        # キャッシュヒット時は fetch() を通らないので、こちらにも入口が要る。
        fetcher = self._fetcher()
        cache_manager = MagicMock()

        with pytest.raises(ValueError) as excinfo:
            list(fetcher.fetch_with_cache(cache_manager, data_spec, "20240101", "20241231"))

        assert RETIRED_DATA_SPECS[data_spec] in str(excinfo.value)
        cache_manager.has_nl_range.assert_not_called()
        cache_manager.read_nl.assert_not_called()

    def test_fetch_with_cache_rejects_a_lowercase_retired_spec(self):
        # CacheManager が spec.upper() で引く以上、小文字でも同じ旧仕様の
        # キャッシュに到達できてしまう。
        fetcher = self._fetcher()
        cache_manager = MagicMock()

        with pytest.raises(ValueError):
            list(fetcher.fetch_with_cache(cache_manager, "diff", "20240101", "20241231"))

        cache_manager.has_nl_range.assert_not_called()

    def test_fetch_with_cache_still_serves_the_replacement(self):
        fetcher = self._fetcher()
        cache_manager = MagicMock()
        cache_manager.has_nl_range.return_value = False

        assert list(fetcher.fetch_with_cache(cache_manager, "DIFN", "20240101", "20241231")) == []

        fetcher.jvlink.jv_open.assert_called_once()

    @pytest.mark.parametrize("data_spec", RETIRED)
    def test_fetch_with_date_range_never_reaches_jvopen(self, data_spec):
        fetcher = self._fetcher()
        start, end = datetime(2024, 1, 1), datetime(2024, 12, 31)

        with pytest.raises(ValueError):
            list(fetcher.fetch_with_date_range(data_spec, start, end))

        fetcher.jvlink.jv_open.assert_not_called()

    def test_fetch_with_date_range_still_opens_the_stream_for_the_replacement(self):
        fetcher = self._fetcher()
        start, end = datetime(2024, 1, 1), datetime(2024, 12, 31)

        assert list(fetcher.fetch_with_date_range("DIFN", start, end, option=3)) == []

        fetcher.jvlink.jv_open.assert_called_once()
        assert fetcher.jvlink.jv_open.call_args.args[0] == "DIFN"


class TestCLIRejectsRetiredSpecs:
    @pytest.mark.parametrize("data_spec,replacement", list(zip(RETIRED, REPLACEMENTS, strict=True)))
    def test_fetch_command_reports_why(self, data_spec, replacement):
        result = CliRunner().invoke(
            cli,
            ["fetch", "--from", "20240101", "--to", "20241231",
             "--spec", data_spec, "--db", "sqlite"],
        )

        assert result.exit_code != 0
        assert "2023-08" in result.output
        assert replacement in result.output

    def test_cache_build_command_reports_why(self):
        result = CliRunner().invoke(
            cli,
            ["cache", "build", "--spec", "DIFF",
             "--from", "20240101", "--to", "20241231"],
        )

        assert result.exit_code != 0
        assert "2023-08" in result.output
        assert "DIFN" in result.output

    def test_cache_build_command_rejects_a_lowercase_retired_spec(self):
        result = CliRunner().invoke(
            cli,
            ["cache", "build", "--spec", "diff",
             "--from", "20240101", "--to", "20241231"],
        )

        assert result.exit_code != 0
        assert "DIFN" in result.output

    def test_cache_rebuild_refuses_via_the_build_step(self):
        # rebuild は「キャッシュを消してから cache build に委譲」する。先に削除が
        # 走ることは許容する方針なので順序は問わず、取り込みに到達せず理由の
        # 分かるエラーで終わることだけを見る。
        with CliRunner().isolated_filesystem():
            result = CliRunner().invoke(
                cli,
                ["cache", "rebuild", "--spec", "DIFF",
                 "--from", "20240101", "--to", "20241231"],
            )

            assert result.exit_code != 0
            assert "2023-08" in result.output
            assert "DIFN" in result.output
