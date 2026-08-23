# JVOpen 読み出し開始/終了ポイント interface worklog — 2026-08-23

## Objective and minimum scope

Answer, and then close, the question of whether jrvltsql exposes the official
`JVOpen` 読み出し開始ポイント / 読み出し終了ポイント interface, and make the
p.17「既知の障害について」workaround usable for the data specs that accept it
(RACE among them).

Minimum scope:

1. add the official `fromtime` contract (both forms, the p.18 end-point
   forbidden dataspec list, and the empty/inverted range) as a validated
   transport guard on both the COM wrapper and the bridge;
2. plumb an explicit read end point through `HistoricalFetcher`,
   `BatchProcessor`, and `jltsql fetch --fromtime-end`;
3. keep the existing option-3/4 start-only setup contract and the existing
   option-1/2 cursor contract unchanged when no end point is requested; and
4. refuse to record an NL cache range as complete for a provider-bounded read.

Out of scope: record parsers, schemas, realtime collection, service-key or
registration handling, and any automatic derivation of a provider bound from
`--to`.

## Official oracle

- `https://jra-van.jp/dlb/sdv/sdk/JV-Link4901.pdf`, SHA-256
  `dfd1c425a62304bb464f15c25106e030ffccbf99c7c777972d6bb6b6d27ef1d7`,
  65 pages, read as text on 2026-08-23.
- p.17 `fromtime` form 1: 開始ポイント時刻のみ `YYYYMMDDhhmmss`. 対象は
  「指定した時刻より大きくかつ現在時刻まで」.
- p.18 form 2: 開始と終了を半角ハイフンで結合した
  `YYYYMMDDhhmmss-YYYYMMDDhhmmss`. 対象は「開始時刻より大きくかつ指定した
  終了時刻まで」.
- p.18 forbidden list: `TOKU` / `DIFF` / `DIFN` / `HOSE` / `HOSN` / `HOYU` /
  `COMM`. 「指定した場合、戻り値：-1(該当データなし)が出力されます」。
  つまり失敗はエラーコードではなく空の成功として現れる。
- p.20 option table: option 1 と 2 は終了時刻がそのまま取得範囲の上限になる。
  option 3/4 は「前月までのデータ」を `fromtime` より大きい全件返し、終了時刻が
  制限するのは今月の通常データ部分だけ。
- p.17 既知の障害: 「dataspec を複数個指定した場合……対象ファイル数が多い場合に
  JVRead の処理時間が遅くなる」。回避策として dataspec の個別指定、または
  `fromtime` への読み出し開始/終了ポイント指定を挙げる。

`RACE` は p.18 の禁止リストに無く、p.20 の option 1/2 で終了時刻が範囲上限に
なる。よって RACE + option 1/2 での終了ポイント指定は公式契約どおり有効である。

## Initial state (before this iteration)

- `JVLinkWrapper.jv_open` / `JVLinkBridge.jv_open` passed `fromtime` through
  verbatim and the wrapper docstring already described the start-end form, but
  nothing validated the form and no caller ever produced one.
- `_jvopen_fromtime` built `f"{from_date}000000"` for option 1/2 and the
  exclusive previous-day `235959` start for option 3/4 — start-only in every
  mode (PR #238).
- `--to` was, and remains, a client-side record-date filter.
- Net effect: the read start point was implemented; the read **end** point was
  documented and reachable only by a caller that hand-built the string, and
  such a string was neither validated nor produced anywhere in the product.

## Change

- `src/jvlink/constants.py`
  - `JVOPEN_END_POINT_FORBIDDEN_DATA_SPECS` (p.18 list),
    `JVOPEN_END_POINT_OPTIONS = (1, 2)` (p.20),
    `jvopen_end_point_forbidden_components`, `supports_jvopen_end_point`,
    `normalize_jvopen_read_point`, `format_jvopen_fromtime`,
    `split_jvopen_fromtime`, `validate_jvopen_fromtime`.
  - A concatenated dataspec supports an end point only if every four-character
    component does; one forbidden component turns the whole request into -1.
- `src/jvlink/wrapper.py`, `src/jvlink/bridge.py`: validate `fromtime` before
  the COM call / before transmission, next to the existing dataspec-option
  guard. An unofficial form would earn -112/-113; a forbidden end point would
  earn a silent -1.
- `src/fetcher/historical.py`: `validate_jvopen_end_point` (spec, option, and
  timestamp), `_jvopen_fromtime(from_date, option, fromtime_end)`, and
  `fetch` / `fetch_with_cache` accept `fromtime_end`. Setup (option 3/4)
  refuses an end point, citing p.20.
- `src/importer/batch.py`: `process_date_range(..., fromtime_end=None)`.
- `src/cli/main.py`: `jltsql fetch --fromtime-end`, validated before any
  database or schema side effect, plus notes — including one that points an
  unbounded fetch at the p.17 workaround.

## Decisions and their reasons

- **`--to` does not become the end point.** The read points are provider
  timestamps (ファイルタイムスタンプ); `--to` filters 開催日. A race inside the
  requested range can have data provided after it (成績 delivered the next day
  or later). Deriving the bound from `--to` would silently drop that data, so
  the bound stays explicit and opt-in.
- **A bounded read never marks an NL cache range complete.** For the same
  reason, such a fetch cannot be claimed to cover the requested date range.
  `fetch_with_cache` still serves an existing complete range from cache.
- **Setup keeps its start-only contract.** p.20 says the end timestamp does not
  bound the historical setup tail, so an end point there would only cut the
  current-month portion while the long tail — the actual cost — stays. The
  request is refused with that reason instead of being silently ignored.
- **Forbidden specs fail closed.** JV-Link answers -1, which the fetcher
  otherwise reports as "no data available". A silent empty success is the worst
  outcome for a data-collection run, so the request is rejected before it is
  sent, at every layer that can build one.

## Tests

- New: `tests/test_jvopen_read_point_contract.py` (63 tests) — fromtime forms,
  the p.18 forbidden list, transport guards on both the COM wrapper and the
  bridge, the fetcher's built `fromtime`, the cache-completion refusal, and the
  CLI wiring/rejections.
- Updated call-shape assertions that pin the single-open setup contract:
  `tests/test_batch_processor.py` (3), `tests/test_historical_cache_failures.py`
  (1). They now show the explicit `None` end point.
- `pytest tests --ignore=tests/integration --ignore=tests/e2e -m "not slow"`:
  4777 passed, 503 skipped, 14 deselected, 21 subtests passed.
- `python scripts/validate_test_gate.py`: TEST GATE PASS.

## Not proven here

- No authenticated provider run was made in this iteration. The claim that a
  bounded RACE option-1 open reduces enumerated/downloaded file counts rests on
  the official p.17/p.20 text, not on a measurement from this environment. A
  timed before/after `readcount` comparison on a registered JV-Link is the
  evidence that would close that gap.
