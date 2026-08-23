"""``fetch`` は複数 dataspec を 1 JV-Link セッションで指定順に処理する。

公式仕様は「dataspec を複数指定すると対象ファイル数が多い場合に JVRead が遅く
なる」を既知障害として挙げ、回避策に「dataspec を個別に指定」を挙げている。
したがって連結して 1 回の JVOpen にはせず、**JVOpen は dataspec ごと・セッション
だけ 1 本**にする。並べ替えは呼び出し側の持ち物なので jltsql では行わない。
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli.main import cli
from src.fetcher.base import FetcherError

EXAMPLE_CONFIG = (
    Path(__file__).resolve().parents[1] / "config" / "config.yaml.example"
)

STATS = {
    "records_fetched": 10,
    "records_parsed": 9,
    "records_imported": 8,
    "records_failed": 1,
    "batches_processed": 2,
}

# 単一 --spec の出力は #290 の前後で一字一句変わってはいけない。rich の折り返しを
# 固定するため COLUMNS を固定した上で丸ごと突き合わせる。
SINGLE_SPEC_GOLDEN = """\
Fetching historical data from JRA-VAN DataLab...

  Data source: JRA (中央競馬)
  Date range: 20260820 -- 20260821
  Data spec:  RACE
  Option:     1 (通常データ)
  Database:   sqlite
Note: --to は取得後のクライアント側日付フィルタであり、JVOpen の終端ではありません。
Note: option=1/2 では --to は JVOpen の終端にならず、狭めてもサーバからのダウンロード量は減りません。
Note: --to は Year+MonthDay または ChokyoDate（HC/WC の調教日）で判定します。対応する日付を持たないレコードは JV-Link 取得時に除外されず、その取得範囲は完全キャッシュとして記録されません。

Processing data...

[OK] Fetch complete!

Statistics:
  Fetched:  10
  Parsed:   9
  Imported: 8
  Failed:   1
  Batches:  2
"""


def _runner():
    # rich の折り返し幅を固定して出力を決定的にする。
    return CliRunner(env={"COLUMNS": "200", "TERM": "dumb"})


def _invoke(specs, *, option=1, side_effect=None, batch_processor=None):
    """``fetch`` を実行し、``(result, batch_processor_mock, processor_mock)`` を返す。"""
    processor = MagicMock()
    if side_effect is not None:
        processor.process_date_range.side_effect = side_effect
    else:
        processor.process_date_range.return_value = STATS

    factory = MagicMock(return_value=processor)
    create_database = MagicMock(return_value=MagicMock())

    args = ["--config", "config.yaml", "fetch", "--from", "20260820", "--to", "20260821"]
    for spec in specs:
        args += ["--spec", spec]
    args += ["--option", str(option), "--db", "sqlite", "--no-cache", "--no-progress"]

    runner = _runner()
    with runner.isolated_filesystem():
        Path("config.yaml").write_text(
            EXAMPLE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8"
        )
        with (
            patch("src.importer.batch.BatchProcessor", factory),
            patch("src.database.create_database_from_config", create_database),
            patch("src.database.schema.create_all_tables"),
        ):
            result = runner.invoke(cli, args)
    return result, factory, processor, create_database


def _processed_specs(processor):
    return [call.kwargs["data_spec"] for call in processor.process_date_range.call_args_list]


def test_single_spec_output_is_unchanged():
    result, _, processor, _ = _invoke(["RACE"])

    assert result.exit_code == 0, result.output
    assert result.output == SINGLE_SPEC_GOLDEN
    assert _processed_specs(processor) == ["RACE"]


def test_one_jvlink_session_serves_every_spec():
    """BatchProcessor は 1 個だけ。spec ごとに作り直すと #287 の効果が消える。

    ``BatchProcessor.__init__`` が ``HistoricalFetcher`` を 1 個作り、その生成時に
    JVInit が走る。spec ごとに作り直すと option=4 の取得元ダイアログが spec 数ぶん
    出てしまい、このチケットの前提そのものが崩れる。
    """
    result, factory, processor, _ = _invoke(["DIFN", "WOOD", "SLOP"])

    assert result.exit_code == 0, result.output
    assert factory.call_count == 1
    assert processor.process_date_range.call_count == 3


def test_specs_are_processed_in_the_order_given():
    """並べ替えは keibaai_cloud の持ち物（ADR-0025）。指定順をそのまま守る。"""
    result, _, processor, _ = _invoke(["WOOD", "BLDN", "DIFN", "RACE"])

    assert result.exit_code == 0, result.output
    assert _processed_specs(processor) == ["WOOD", "BLDN", "DIFN", "RACE"]


def test_each_spec_repeats_the_header_and_statistics_block():
    """出力の口は増やさない。既存ブロックを dataspec ごとに繰り返すだけ。"""
    result, _, _, _ = _invoke(["DIFN", "WOOD", "SLOP"])

    assert result.exit_code == 0, result.output
    assert result.output.count("[OK] Fetch complete!") == 3
    assert result.output.count("Statistics:") == 3
    for spec in ("DIFN", "WOOD", "SLOP"):
        assert f"  Data spec:  {spec}" in result.output


def test_the_date_range_and_option_are_the_same_for_every_spec():
    result, _, processor, _ = _invoke(["DIFN", "RACE"], option=4)

    assert result.exit_code == 0, result.output
    for call in processor.process_date_range.call_args_list:
        assert call.kwargs["from_date"] == "20260820"
        assert call.kwargs["to_date"] == "20260821"
        assert call.kwargs["option"] == 4


def test_a_failing_spec_stops_the_run_before_the_next_one():
    """ADR-0023「止めて人に見せる」。以降を実行せず、終了コードで分かる。"""
    result, _, processor, _ = _invoke(
        ["DIFN", "WOOD", "SLOP"],
        side_effect=[STATS, FetcherError("Historical fetch failed: boom"), STATS],
    )

    assert result.exit_code != 0
    assert _processed_specs(processor) == ["DIFN", "WOOD"]
    assert "boom" in result.output


def test_setup_dialog_cancel_stops_the_whole_run():
    """取得元の選択が拒否された以上、後続も初回の選択を引き継げない。"""
    result, _, processor, _ = _invoke(
        ["DIFN", "WOOD"],
        option=4,
        side_effect=[
            FetcherError(
                "Historical fetch failed: JVOpen setup dialog was cancelled"
            ),
            STATS,
        ],
    )

    assert result.exit_code != 0
    assert _processed_specs(processor) == ["DIFN"]
    assert "cancel" in result.output


def test_a_retired_spec_anywhere_is_rejected_before_the_database():
    # DIFF は廃止済み（DIFN が後継）。2 番目に置いても DB より先に落ちる。
    result, factory, _, create_database = _invoke(["RACE", "DIFF"])

    assert result.exit_code == 1, result.output
    create_database.assert_not_called()
    factory.assert_not_called()


def test_an_invalid_option_combination_anywhere_is_rejected_before_the_database():
    # DIFN は option=2（今週データ）では取得できない。
    result, factory, _, create_database = _invoke(["RACE", "DIFN"], option=2)

    assert result.exit_code == 1, result.output
    assert "DIFN" in result.output
    create_database.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize("specs", [["RACE", "RACE"], ["DIFN", "RACE", "DIFN"]])
def test_a_repeated_spec_is_processed_once_per_occurrence(specs):
    """重複の除去も呼び出し側の判断。jltsql は指定された回数だけ回す。"""
    result, _, processor, _ = _invoke(specs)

    assert result.exit_code == 0, result.output
    assert _processed_specs(processor) == specs
