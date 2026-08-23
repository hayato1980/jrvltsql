#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JVGets の実機 probe（手動・Windows 実機専用）

keibaai_cloud#253 のスコープ 1 をそのまま実行する。pytest でも release gate でも
なく、JV-Link が入った VM で人が 1 回走らせて、結果を Issue に貼るためのもの。

観測するのは 4 点:

1. 3 引数の ``JVGets(bytearray(), size, bytearray())`` が ``rc>0`` を返すか
2. その後 ``JVClose`` が ``rc=0`` で返るか
3. 同じ範囲を ``JVRead`` と ``JVGets`` で読んで、バイト列が一致するか
   （往復変換の損失を直接測る対照。一致しない位置は 16 進で出す）
4. 長めに回したときのメモリ挙動（``--soak-records``）

3 は 1 本のストリームから同じレコードを 2 回読めないので、同じ ``JVOpen`` を
2 回開いて読み比べる。あわせて所要時間も出す。#253 の 2026-08-23 のコメントで
分かったとおり、``full`` の律速は JV-Link の COM サーバ（``dllhost``）の中に
あって python 側のプロファイルには映らないので、**切り分けになるのは python の
プロファイルではなく、この 2 パスの所要時間の差**である。

``option=1`` の差分取得なので setup ダイアログは出ず、SSM から回せる。ただし
JV-Link は単一インスタンスなので、``full`` の実走中は同時に走らせないこと。

使い方（VM 上）::

    python tools/manual/probe_jvgets.py --spec RACE --from 20260801000000 \\
        --records 200 --soak-records 20000

JV-Link のネイティブ COM を直接叩く。JSON ブリッジ経由では ``jv_gets`` は
``jv_read`` へ委譲されるだけで、本 probe の問いには答えられない。
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.jvlink.wrapper import JVLinkError, JVLinkWrapper  # noqa: E402

JV_READ_DOWNLOAD_POLL_SECONDS = 0.2
JV_READ_DOWNLOAD_TIMEOUT_SECONDS = 300.0


def _resident_bytes() -> Optional[int]:
    """Windows の作業セットを返す。取れなければ None。"""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = _PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(counters)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if not ctypes.windll.psapi.GetProcessMemoryInfo(
        handle, ctypes.byref(counters), counters.cb
    ):
        return None
    return int(counters.WorkingSetSize)


def _read_one(wrapper: JVLinkWrapper, use_gets: bool) -> Tuple[int, Optional[bytes]]:
    """1 レコード読む。-3（ダウンロード待ち）はここで吸収する。"""
    waited_since: Optional[float] = None
    while True:
        if use_gets:
            ret_code, buff, _filename = wrapper.jv_gets()
        else:
            ret_code, buff, _filename = wrapper.jv_read()

        if ret_code != -3:
            return ret_code, buff

        now = time.monotonic()
        if waited_since is None:
            waited_since = now
        elif now - waited_since >= JV_READ_DOWNLOAD_TIMEOUT_SECONDS:
            raise JVLinkError(
                f"file-downloading wait timeout after {now - waited_since:.1f} seconds"
            )
        time.sleep(JV_READ_DOWNLOAD_POLL_SECONDS)


def _drain(
    wrapper: JVLinkWrapper,
    limit: int,
    use_gets: bool,
    keep: bool,
    sample_every: int = 0,
) -> dict:
    """limit レコードまで読む。keep=True のときだけバイト列を保持する。"""
    records: List[bytes] = []
    read = 0
    file_switches = 0
    samples: List[dict] = []
    started = time.perf_counter()

    while read < limit:
        ret_code, buff = _read_one(wrapper, use_gets)

        if ret_code == 0:
            break
        if ret_code == -1:
            file_switches += 1
            continue
        if ret_code < 0:
            raise JVLinkError(
                f"{'JVGets' if use_gets else 'JVRead'} returned {ret_code}",
                error_code=ret_code,
            )

        read += 1
        if keep:
            records.append(buff)
        if sample_every and read % sample_every == 0:
            samples.append({"records": read, "resident_bytes": _resident_bytes()})

    elapsed = time.perf_counter() - started
    return {
        "records": read,
        "file_switches": file_switches,
        "elapsed_seconds": round(elapsed, 3),
        "records_per_second": round(read / elapsed, 1) if elapsed > 0 else None,
        "bytes": records,
        "memory_samples": samples,
    }


def _pass(
    sid: str,
    spec: str,
    fromtime: str,
    option: int,
    limit: int,
    use_gets: bool,
    keep: bool,
    sample_every: int = 0,
) -> dict:
    """JVOpen → 読み出し → JVClose を 1 往復する。"""
    wrapper = JVLinkWrapper(sid)
    init_code = wrapper.jv_init()
    open_code, read_count, download_count, last_timestamp = wrapper.jv_open(
        spec, fromtime, option
    )
    try:
        result = _drain(wrapper, limit, use_gets, keep, sample_every)
    finally:
        close_code = wrapper.jv_close()

    result.update(
        {
            "method": "JVGets" if use_gets else "JVRead",
            "jv_init": init_code,
            "jv_open": open_code,
            "read_count": read_count,
            "download_count": download_count,
            "last_file_timestamp": last_timestamp,
            "jv_close": close_code,
        }
    )
    return result


def _compare(read_bytes: List[bytes], gets_bytes: List[bytes]) -> dict:
    """バイト列を突き合わせ、最初の食い違いを 16 進で示す。"""
    compared = min(len(read_bytes), len(gets_bytes))
    for index in range(compared):
        left, right = read_bytes[index], gets_bytes[index]
        if left == right:
            continue
        offset = next(
            (i for i, (a, b) in enumerate(zip(left, right)) if a != b),
            min(len(left), len(right)),
        )
        window = slice(max(0, offset - 8), offset + 8)
        return {
            "identical": False,
            "compared_records": compared,
            "first_mismatch": {
                "record_index": index,
                "byte_offset": offset,
                "jvread_length": len(left),
                "jvgets_length": len(right),
                "jvread_hex": left[window].hex(" "),
                "jvgets_hex": right[window].hex(" "),
            },
        }

    return {
        "identical": len(read_bytes) == len(gets_bytes),
        "compared_records": compared,
        "jvread_records": len(read_bytes),
        "jvgets_records": len(gets_bytes),
    }


def _interleave(sid: str, spec: str, fromtime: str, option: int, limit: int) -> dict:
    """JVRead と JVGets を交互に呼んでもレコードが落ちないことを見る.

    公式仕様書が「交互に呼ばれたとしても矛盾なくレコードが取得できる」と書いて
    いる箇所。これが本当なら、呼び出し側を 1 か所ずつ移せる（退避も効く）。
    """
    wrapper = JVLinkWrapper(sid)
    wrapper.jv_init()
    wrapper.jv_open(spec, fromtime, option)
    lengths: List[Tuple[str, int]] = []
    try:
        while len(lengths) < limit:
            use_gets = len(lengths) % 2 == 1
            ret_code, buff = _read_one(wrapper, use_gets)
            if ret_code == 0:
                break
            if ret_code == -1:
                continue
            if ret_code < 0:
                raise JVLinkError(f"interleaved read returned {ret_code}", error_code=ret_code)
            lengths.append(("JVGets" if use_gets else "JVRead", len(buff)))
    finally:
        close_code = wrapper.jv_close()

    return {
        "records": len(lengths),
        "jv_close": close_code,
        "sequence": [{"method": m, "length": n} for m, n in lengths[:20]],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sid", default="UNKNOWN", help="JV-Link SID")
    parser.add_argument("--spec", default="RACE", help="dataspec (default: RACE)")
    parser.add_argument(
        "--from",
        dest="fromtime",
        required=True,
        help="JVOpen の fromtime（YYYYMMDDhhmmss）",
    )
    parser.add_argument(
        "--option", type=int, default=1, help="JVOpen option（既定 1: 差分取得）"
    )
    parser.add_argument(
        "--records", type=int, default=200, help="読み比べるレコード数（既定 200）"
    )
    parser.add_argument(
        "--interleave-records",
        type=int,
        default=20,
        help="交互呼び出しで読むレコード数（0 で省略）",
    )
    parser.add_argument(
        "--soak-records",
        type=int,
        default=0,
        help="JVGets だけで長めに回すレコード数（0 で省略）",
    )
    parser.add_argument(
        "--soak-sample-every",
        type=int,
        default=5000,
        help="soak 中にメモリを記録する間隔（レコード数）",
    )
    args = parser.parse_args()

    if args.option in (3, 4):
        print(
            "警告: option=3/4 は JVOpen がセットアップダイアログを出す。"
            "session 0 では不可視のまま待ち続ける。",
            file=sys.stderr,
        )

    summary: dict = {
        "spec": args.spec,
        "fromtime": args.fromtime,
        "option": args.option,
        "resident_bytes_at_start": _resident_bytes(),
    }

    read_pass = _pass(
        args.sid, args.spec, args.fromtime, args.option, args.records, False, True
    )
    gets_pass = _pass(
        args.sid, args.spec, args.fromtime, args.option, args.records, True, True
    )

    summary["comparison"] = _compare(read_pass.pop("bytes"), gets_pass.pop("bytes"))
    read_pass.pop("memory_samples", None)
    gets_pass.pop("memory_samples", None)
    summary["jvread_pass"] = read_pass
    summary["jvgets_pass"] = gets_pass

    if gets_pass["elapsed_seconds"] > 0:
        summary["jvread_over_jvgets"] = round(
            read_pass["elapsed_seconds"] / gets_pass["elapsed_seconds"], 2
        )

    if args.interleave_records:
        summary["interleaved"] = _interleave(
            args.sid, args.spec, args.fromtime, args.option, args.interleave_records
        )

    if args.soak_records:
        soak = _pass(
            args.sid,
            args.spec,
            args.fromtime,
            args.option,
            args.soak_records,
            True,
            False,
            args.soak_sample_every,
        )
        soak.pop("bytes", None)
        soak["resident_bytes_at_end"] = _resident_bytes()
        summary["soak"] = soak

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    identical = summary["comparison"].get("identical")
    return 0 if identical else 1


if __name__ == "__main__":
    sys.exit(main())
