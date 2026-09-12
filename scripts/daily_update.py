#!/usr/bin/env python
"""Non-interactive daily JRA sync for Windows task scheduling."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.database import create_database_from_config
from src.importer.batch import BatchProcessor
from src.realtime import speed_report
from src.utils.config import load_config

UPDATE_SPECS = [
    ("TOKU", 2),
    ("RACE", 2),
    # Master deltas keep UM/KS/CH/BR/BN current after the initial DIFN setup.
    ("DIFN", 1),
    ("TCVN", 2),
    ("RCVN", 2),
    # Training data is updated daily and must be collected incrementally.
    # HC=坂路調教, WC=ウッドチップ調教. option=1 is the incremental fetch.
    ("SLOP", 1),
    ("WOOD", 1),
    # MING=データマイニング予想 (DM レコード -> NL_DM)。SE の mining ブロック
    # (DMTime/DMJyuni/KyakusituKubun) と NL_DM を供給する。option=1 の
    # incremental。レース当日発表のため過去分の一括 backfill は不可
    # (前向きにのみ蓄積される)。
    ("MING", 1),
    # Speed-report specs fetched via JVRTOpen with a date key (option unused).
    # 0B12: 速報レース情報・払戻 (RA/SE/HR 成績確定後), 0B15: 速報レース情報
    # (RA/SE/HR 出走馬名表～)。RT_* テーブルは PRIMARY KEY + INSERT OR REPLACE
    # なので再実行しても重複しない（冪等）。
    ("0B12", 1),
    ("0B15", 1),
    # 0B14: 速報開催情報・一括。WE(天候馬場状態)/
    # AV(出走取消・除外)/JC/TC/CC を供給する。WE は NL 蓄積が存在しない
    # 速報専用レコードで、RT_WE を埋める唯一の経路。RT_* は PRIMARY KEY +
    # INSERT OR REPLACE で冪等。レース当日発表のため過去分 backfill は不可
    # (前向きにのみ蓄積)。過去の馬場状態は RA レコード側(field50/51)が供給する。
    ("0B14", 1),
    # 0B16 is event-keyed (JVWatchEvent), not YYYYMMDD-keyed.
    ("0B51", 1),
]

REALTIME_SPEC_PREFIX = "0B"

# 購読エラー(-111/-114/-115)の扱いは速報系の 1 周実装と同じものを使う。MING 等の
# 任意契約スペックが未購読でも日次同期を止めないよう、これらは
# --ignore-jvopen-error-codes の指定に関わらず警告してスキップする。
SUBSCRIPTION_ERROR_CODES = speed_report.SUBSCRIPTION_ERROR_CODES


def _is_realtime_spec(spec: str) -> bool:
    """Return True for JVRTOpen speed-report specs (e.g., 0B12, 0B15)."""

    return spec.upper().startswith(REALTIME_SPEC_PREFIX)


# 日付キーの速報系を 1 周で取り切る実装は src/realtime/speed_report.py が持つ。
# 日次同期と、1 周だけ回したい呼び出し側の両方が同じ drain ループを使う。
_iter_date_keys = speed_report.iter_date_keys
_sync_realtime_spec = speed_report.sync_date_keyed_spec


def _select_update_specs(specs: str | None) -> list[tuple[str, int]]:
    """Resolve a comma-separated spec allowlist against UPDATE_SPECS."""

    if not specs:
        return UPDATE_SPECS
    options = {spec: option for spec, option in UPDATE_SPECS}
    selected: list[tuple[str, int]] = []
    for raw in specs.split(","):
        spec = raw.strip().upper()
        if not spec:
            continue
        if spec not in options:
            raise ValueError(f"Unsupported daily update spec: {spec}")
        selected.append((spec, options[spec]))
    return selected


def _force_incremental_options(specs: list[tuple[str, int]]) -> list[tuple[str, int]]:
    """Use normal incremental JVOpen for task-scheduler smoke/recovery runs."""

    return [(spec, 1 if option == 2 else option) for spec, option in specs]


def _parse_ignored_error_codes(value: str | None) -> set[int]:
    if not value:
        return set()
    return {int(part.strip()) for part in value.split(",") if part.strip()}


def _error_code_from_exception(exc: Exception) -> int | None:
    match = re.search(r"code:\s*(-?\d+)", str(exc))
    return int(match.group(1)) if match else None


def _effective_option(spec: str, configured_option: int, from_date: str) -> int:
    """Apply quickstart's setup fallback for specs that need full refresh."""

    if spec != "DIFN" or configured_option != 1:
        return configured_option
    from_date_dt = datetime.strptime(from_date, "%Y%m%d")
    now = datetime.now()
    months_ago = (now.year * 12 + now.month) - (from_date_dt.year * 12 + from_date_dt.month)
    return 4 if months_ago > 11 else configured_option


def main() -> int:
    parser = argparse.ArgumentParser(description="Run daily JRA incremental sync")
    parser.add_argument("--config", default=None, help="Path to config.yaml")
    parser.add_argument("--days-back", type=int, default=7, help="Fetch window size in days")
    parser.add_argument(
        "--days-forward", type=int, default=0, help="Fetch future card window size in days"
    )
    parser.add_argument(
        "--db", default=None, choices=["sqlite", "postgresql"], help="Override database type"
    )
    parser.add_argument(
        "--ensure-tables",
        dest="ensure_tables",
        action="store_true",
        default=True,
        help="Create/migrate tables before sync (default)",
    )
    parser.add_argument(
        "--no-ensure-tables",
        dest="ensure_tables",
        action="store_false",
        help="Skip table creation/migration before sync",
    )
    parser.add_argument(
        "--specs", default=None, help="Comma-separated subset of daily update specs"
    )
    parser.add_argument(
        "--force-incremental",
        action="store_true",
        help="Use JVOpen option=1 instead of option=2 for selected update specs",
    )
    parser.add_argument(
        "--ignore-jvopen-error-codes",
        default=None,
        help="Comma-separated JVOpen error codes to warn-and-skip for daily tasks",
    )
    args = parser.parse_args()

    config_path = args.config or str(PROJECT_ROOT / "config" / "config.yaml")
    config = load_config(config_path)
    database = create_database_from_config(config, db_type_override=args.db)

    to_date = (datetime.now() + timedelta(days=max(args.days_forward, 0))).strftime("%Y%m%d")
    from_date = (datetime.now() - timedelta(days=max(args.days_back, 1))).strftime("%Y%m%d")

    with database:
        processor = BatchProcessor(
            database=database,
            sid=config.get("jvlink.sid", "JLTSQL"),
            batch_size=1000,
            show_progress=False,
        )
        try:
            update_specs = _select_update_specs(args.specs)
        except ValueError as exc:
            print(f"[daily-sync] {exc}", file=sys.stderr)
            return 2
        if args.force_incremental:
            update_specs = _force_incremental_options(update_specs)
        ignored_error_codes = _parse_ignored_error_codes(args.ignore_jvopen_error_codes)

        for spec, option in update_specs:
            if _is_realtime_spec(spec):
                print(f"[daily-sync] {spec} {from_date}..{to_date} (realtime)")
                try:
                    stats = _sync_realtime_spec(
                        database=database,
                        spec=spec,
                        from_date=from_date,
                        to_date=to_date,
                        sid=config.get("jvlink.sid", "JLTSQL"),
                        ensure_tables=args.ensure_tables,
                    )
                except Exception as exc:
                    code = _error_code_from_exception(exc)
                    if code in ignored_error_codes or code in SUBSCRIPTION_ERROR_CODES:
                        print(
                            f"[daily-sync] {spec} skipped: JVOpen code {code} (unsubscribed/ignored)"
                        )
                        continue
                    raise
                print(
                    f"[daily-sync] {spec} fetched={stats.get('records_fetched', 0)} "
                    f"parsed={stats.get('records_parsed', 0)} "
                    f"imported={stats.get('records_imported', 0)} "
                    f"failed={stats.get('records_failed', 0)}"
                )
                continue
            option = _effective_option(spec, option, from_date)
            print(f"[daily-sync] {spec} {from_date}..{to_date} option={option}")
            try:
                stats = processor.process_date_range(
                    data_spec=spec,
                    from_date=from_date,
                    to_date=to_date,
                    option=option,
                    ensure_tables=args.ensure_tables,
                )
            except Exception as exc:
                code = _error_code_from_exception(exc)
                if code in ignored_error_codes or code in SUBSCRIPTION_ERROR_CODES:
                    print(f"[daily-sync] {spec} skipped: JVOpen code {code} (unsubscribed/ignored)")
                    continue
                raise
            print(
                f"[daily-sync] {spec} fetched={stats.get('records_fetched', 0)} "
                f"parsed={stats.get('records_parsed', 0)} imported={stats.get('records_imported', 0)} "
                f"failed={stats.get('records_failed', 0)}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
