"""One-pass JVRTOpen sync for date-keyed speed-report data specs.

Speed-report specs such as 0B11 (馬体重) and 0B14 (開催情報・一括) are opened
with a YYYYMMDD key, one key per race date. That is a different request shape
from the odds specs, which are opened per race with a YYYYMMDDJJRR key, so the
time-series fetcher rejects these specs before touching JV-Link.

This module holds the drain loop those specs need: open -> drain -> close, once
per date key, and then return. It mirrors ``RealtimeMonitor._drain_key`` but
runs a single pass instead of polling, so a caller that wants periodic refresh
schedules the pass rather than leaving a process resident.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta

# JV-Link は未契約データ種別に対し購読エラーを返す (-111 契約無し / -114 未購読
# 一括 / -115 未購読当該)。任意契約のスペックが未購読でも同期全体を止めないよう、
# これらは呼び出し側の ignore 指定に関わらず警告してスキップする。
SUBSCRIPTION_ERROR_CODES = frozenset({-111, -114, -115})

# 0B14 は「その時点の完全なスナップショット」を返す。取り消された変更は以後の
# 応答から単に消えるため、upsert だけでは古い行が残る。
SNAPSHOT_REPLACED_SPEC = "0B14"


def iter_date_keys(from_date: str, to_date: str) -> list[str]:
    """Return inclusive YYYYMMDD keys between from_date and to_date."""

    start = datetime.strptime(from_date, "%Y%m%d")
    end = datetime.strptime(to_date, "%Y%m%d")
    if end < start:
        return []
    return [
        (start + timedelta(days=offset)).strftime("%Y%m%d")
        for offset in range((end - start).days + 1)
    ]


def sync_date_keyed_spec(
    database,
    spec: str,
    from_date: str,
    to_date: str,
    sid: str,
    jvlink=None,
    updater=None,
    ensure_tables: bool = True,
) -> dict:
    """Fetch a date-keyed JVRTOpen speed-report spec and upsert its rows.

    Opens, drains and closes one JVRTOpen stream per date key and then returns.
    Imports are idempotent because RealtimeUpdater uses INSERT OR REPLACE on
    primary keys, and 0B14 additionally clears the previous snapshot for the
    date before inserting its replacement.

    Args:
        database: Open database handler.
        spec: Date-keyed speed-report data spec (e.g., "0B11", "0B14").
        from_date: Start date YYYYMMDD (inclusive).
        to_date: End date YYYYMMDD (inclusive).
        sid: JV-Link session ID.
        jvlink: Optional JV-Link wrapper override. When supplied the caller owns
            the JV-Link session: ``jv_init`` is not called here, which is how a
            caller runs several specs inside one session.
        updater: Optional RealtimeUpdater override (tests).
        ensure_tables: Create/migrate tables before the first open.

    Returns:
        Counter dict with records_fetched / records_parsed / records_imported /
        records_failed.
    """

    from src.jvlink.bridge import JVLinkBridgeError
    from src.jvlink.wrapper import JVLinkError
    from src.database.schema import create_all_tables
    from src.realtime.updater import RealtimeUpdater, summarize_update_result

    if ensure_tables:
        create_all_tables(database)

    database.begin_transaction()

    owns_jvlink = jvlink is None
    if jvlink is None:
        from src.fetcher.realtime import RealtimeFetcher

        jvlink = RealtimeFetcher(sid=sid).jvlink
    if updater is None:
        updater = RealtimeUpdater(database=database)

    stats = {
        "records_fetched": 0,
        "records_parsed": 0,
        "records_imported": 0,
        "records_failed": 0,
    }

    try:
        if owns_jvlink:
            jvlink.jv_init()
        for key in iter_date_keys(from_date, to_date):
            try:
                ret, _count = jvlink.jv_rt_open(spec, key)
            except (JVLinkError, JVLinkBridgeError) as exc:
                code = getattr(exc, "error_code", None)
                if code in SUBSCRIPTION_ERROR_CODES:
                    print(f"[speed-report] {spec} not subscribed, skipping spec")
                    break
                raise
            if ret == -1:
                # No data published for this date key (normal).
                continue
            if ret < -1:
                raise RuntimeError(f"{spec} {key} JVRTOpen failed: {ret}")
            try:
                if spec == SNAPSHOT_REPLACED_SPEC:
                    updater.replace_date_snapshot(key)
                while True:
                    ret_code, buff, _fname = jvlink.jv_read()
                    if ret_code == 0:
                        break
                    if ret_code == -1:
                        # File switch; keep reading.
                        continue
                    if ret_code < 0:
                        raise RuntimeError(f"{spec} {key} JVRead failed: {ret_code}")
                    if not buff:
                        raise RuntimeError(f"{spec} {key} JVRead returned no buffer")
                    stats["records_fetched"] += 1
                    try:
                        result = updater.process_record(buff)
                    except Exception as exc:  # noqa: BLE001 - drain, then fail closed
                        stats["records_failed"] += 1
                        print(
                            f"[speed-report] {spec} {key} record failed: {exc}",
                            file=sys.stderr,
                        )
                        continue
                    successful, failed = summarize_update_result(result)
                    stats["records_parsed"] += len(successful) + failed
                    stats["records_imported"] += len(successful)
                    stats["records_failed"] += failed
            finally:
                try:
                    jvlink.jv_close()
                except Exception:
                    pass
        if stats["records_failed"]:
            raise RuntimeError(
                f"{spec} realtime import rejected " f"{stats['records_failed']} record(s)"
            )
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        if owns_jvlink:
            try:
                jvlink.jv_close()
            except Exception:
                pass
    return stats
