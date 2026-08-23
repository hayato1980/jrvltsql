# jrvltsql 全体性能レビュー — 2026-08-23

## 目的と範囲

- 目的: `src/` 全体を性能の観点でレビューし、取得 → parse → 検証 → 変換 → 保存
  の各段でどこに時間が消えているかを実測で特定する。
- 対象 HEAD: `34a3297`（`2.0.0.dev5`）。
- 本ドキュメントはレビュー結果のみで、コード変更は含まない。

## 計測環境と、その限界

| 項目 | 値 |
| --- | --- |
| OS / CPU | Linux x86_64（コンテナ） |
| Python | 3.12.3（`uv venv` + `pip install -e ".[dev]"`） |
| DB | SQLite（`SQLiteDatabase`、既定 PRAGMA のまま） |
| 入力 | `tests/fixtures/record_factory.py` の公式レイアウト合成レコード、および本レビュー用に組んだ O1 / O6 の公式長レコード |
| 計測 | `time.perf_counter` と `cProfile` |

**この数値をそのまま本番の所要時間として読まないこと。**

- リリース検証済み経路は Windows + 32-bit Python + JV-Link COM である。COM の
  `JVRead` 往復と JRA-VAN 側のダウンロードは本計測に含まれていない。実運用では
  そちらが支配的な区間もある。
- SQLite ローカルファイルでの計測なので、PostgreSQL のネットワーク往復は
  含まれない。PostgreSQL 固有の指摘（P6〜P8）は静的解析に基づく。
- 以下の「%」は、すべて **計測したプロセス内処理に占める割合** であって、
  実運用の壁時計時間に占める割合ではない。

## 全体像 — どこに時間が消えているか

計測したスループット:

| 経路 | 実測 |
| --- | --- |
| RA parse（962〜1,272 byte 固定長 → dict） | 約 9,900 rec/s（101 µs/レコード） |
| RA import（parse 済み dict → SQLite） | 約 5,400 rec/s（185 µs/レコード） |
| O1 import（300 物理レコード = 19,200 展開行） | 7.0 ms/物理レコード |
| O6 parse（83,285 byte → 4,896 展開行） | 31.9 ms/物理レコード |

import 側の `cProfile`（RA 5,000 件、tottime 順）:

```
   ncalls  tottime  cumtime  function
     5000    0.545    0.873  importer.py:7765(convert_record_types)
     5000    0.169    0.334  importer.py:5379(clean_record_metadata)
   615000    0.133    0.225  database/base.py:270(<genexpr>)   # insert_many の値抽出
        5    0.092    0.092  {method 'executemany' of 'sqlite3.Cursor'}
        5    0.083    0.401  database/base.py:220(insert_many)
```

**取り込みの実質的なボトルネックは DB ではない。** SQLite への
`executemany` は全体の約 4%、`insert_many` 全体でも約 18% で、残りの
8 割は Python 側の dict 変換・検証である。`convert_record_types` 単独で
取り込み時間の約 40% を占める。

parse 側は別の一点に集中している。RA の profile では
`bytes.decode` が 230,000 回で tottime 0.161 秒 / 全体 0.462 秒。
**parse 時間の約 75% が cp932 デコードそのもの**である。

つまり最適化の的は 3 つに絞れる。

1. 展開行（オッズ・マイニング）の無駄な往復
2. cp932 デコード
3. `convert_record_types` / `clean_record_metadata` の per-field 定数判定

---

## P1（最重要）— 捨てられる展開行が、捨てられる前に全検証を通っている

### 事実

`DataImporter.import_records` のループはこの順で進む。

- `src/importer/importer.py:8314` — `validate_import_record_header(record)`
- `src/importer/importer.py:8317` — `self._get_table_name(record_type)`
- `src/importer/importer.py:8322-8397` — 約 20 組の
  `verify_*_storage_schema` / `validate_*_record`（うち
  `src/importer/importer.py:8394` が `validate_odds_record`）
- `src/importer/importer.py:8474` — `_is_mining_snapshot_follower` → `continue`
- `src/importer/importer.py:8477` — `_is_odds_snapshot_follower` → `continue`

O1〜O6 の1物理レコードは `odds_domain.attach_snapshot_metadata`
（`src/parser/odds_domain.py:205`）で N 行に展開され、先頭行だけが
`replace_odds_native_snapshot` で丸ごと使われる。残る N-1 行は
`_is_odds_snapshot_follower` で捨てられる。
**その N-1 行が、捨てられる直前まで全検証を通っている。**

`import_single_record` も同型（`src/importer/importer.py:9053` /
`9187` / `9305`）。

### 実測

| | O1（962 byte） | O6（83,285 byte） |
| --- | --- | --- |
| 展開行数 / 物理レコード | 64 | 4,896 |
| 捨てられる follower 行 | 63（98.4%） | 4,895（99.98%） |
| `validate_odds_record` | 15.9 µs/行 | 22.7 µs/行 |
| `_is_odds_snapshot_follower` | 2.7 µs/行 | 3.6 µs/行 |
| **follower に費やす検証（後述 P2 の二重実行込み）** | **約 2.0 ms/物理** | **約 222 ms/物理** |
| follower 判定を先に置いた場合 | 約 0.17 ms | 約 17.8 ms |

O1 の取り込み実測 7.0 ms/物理レコードのうち、この無駄が約 2 ms（29%）。
O6 では parse 31.9 ms に対して **222 ms** が捨てる行の検証に消える。

README が挙げる `TS_SOKUHO_O1`〜`TS_SOKUHO_O6`（開催週の全賭式速報オッズ）は
まさに O6 を高頻度スナップショットで取り込む経路で、ここが直撃する。

### 対処

1. **最小の修正**: `_is_mining_snapshot_follower` /
   `_is_odds_snapshot_follower` の判定を `_get_table_name()` の直後
   （`src/importer/importer.py:8320` 付近）へ移す。判定自体は 2.7〜3.6 µs/行と
   安く、`_odds_native_snapshot_rows` はレコード内の値しか見ないので
   検証済みであることに依存していない。`import_single_record` も同様。
2. **本命**: そもそも follower 行を fetcher の generator に流さない。
   `attach_snapshot_metadata` が「先頭行 + スナップショット全行」を
   1 レコードとして返せば、O6 で 4,896 → 1 レコードになり、
   `src/fetcher/base.py:229` の `record_item["_raw"] = buff` も
   `_is_within_date_range` も 1 回で済む。ただし展開行を1件ずつ数える
   統計・契約テストに影響するので、1 とは別イテレーションで扱うべき。

### 付随

`attach_snapshot_metadata`（`src/parser/odds_domain.py:205-212`）は
`[dict(row) for row in rows]` で全行を複製したうえで `{**row, ...}` で
もう一度作り直す。O6 スケールで **7.81 ms / 4.8 MB（tracemalloc peak）**。
現在の呼び出し元（`o1_parser.py`〜`o6_parser.py`）はいずれも `rows` を
その場で組み立てて他所へ渡していないので、防御的複製 1 回分は削れる。

---

## P2 — 同じレコードの本体検証が 2 回走る

### 事実

`validate_import_record_header`（`src/importer/importer.py:5330-5360`）は
ヘッダ検証だけでなく、`UM` / `H1` / `H6` / `O1`〜`O6` / `CS` / `SE` / `WE`
について**本体フィールド検証まで**呼ぶ。

そのあとループ内で `validate_um_record` / `validate_h1_record` /
`validate_odds_record` / `SEParser.validate_current_fields` 相当が
`src/importer/importer.py:8331-8397` で**もう一度**走る。

### 証拠

O1 を 6,400 行取り込んだ profile で:

```
    12801    odds_domain.py:107(validate_key_fields)
    12801    odds_domain.py:116(validate_header_fields)
```

6,400 行に対して 12,801 回 = ちょうど 2 倍 + 1（先頭ヘッダの事前検証）。

### 対処

責務を分ける。`validate_import_record_header` はヘッダ（RecordSpec /
DataKubun / MakeDate）だけを見る名前どおりの関数にし、本体検証は
テーブル確定後の 1 か所に寄せる。どちらを残すにせよ、
2 回通すことに fail-closed 上の利得はない（同じ入力・同じ検証器）。

---

## P3 — cp932 デコードが parse 時間の約 75%

### 事実

高頻度レコード（RA / SE / O1〜O6 / UM / HR ほか）は `BaseParser` を使わず
自前 `parse` を持ち、フィールドごとに次を呼ぶ。

```python
@staticmethod
def decode_field(data: bytes) -> str:
    return data.decode("cp932", errors="strict").strip()
```

これは **21 個のパーサに同一実装が重複**している
（`src/parser/o1_parser.py:133`、`se_parser.py:116`、`um_parser.py:181`、
`hr_parser.py:83` ほか。`grep -c 'decode("cp932"' src` で 25 か所）。

### 実測

| デコード | 8 byte あたり |
| --- | --- |
| `cp932` | 508 ns |
| `ascii` | 138 ns |
| `latin-1` | 141 ns |

cp932 は Python の高速パス（ASCII / UTF-8）に乗らず、マルチバイトコーデック
機構を通るため 3.7 倍遅い。RA の 107 フィールドではこれだけで
**74.7 µs/レコード**（parse 全体 101 µs の約 74%）。

ASCII 優先 + `UnicodeDecodeError` で cp932 フォールバックにすると、
数値 100 フィールド + 日本語 60 byte × 7 フィールドの現実的な構成で:

```
current cp932-only: 52.98 us/record (107 fields)
ascii-first hybrid: 22.28 us/record (107 fields)
```

**2.4 倍**。cp932 は 0x00–0x7F で ASCII と完全に一致するので、
ASCII でデコードできたスライスの結果は cp932 と同一であり、意味は変わらない。
非 ASCII バイトを含むスライスは `UnicodeDecodeError` で必ず cp932 に落ちる。
レコード全体は `validate_fixed_record`（`src/parser/base.py:45`）で
すでに厳密 cp932 デコード済みなので、fail-closed の性質も保たれる。

### 対処

1. `decode_field` を 1 か所（`src/parser/base.py` か新規
   `src/parser/decode.py`）に集約し、21 個の重複を消す。
2. その 1 か所を ASCII 優先ハイブリッドにする。
   1 か所直せば全パーサに効く、という状態を先に作るのが要点。

なお「byte でスライスしてからデコードする」設計そのものは正しい
（`src/parser/base.py:169-171` のコメントどおり、先に全体をデコードすると
CP932 のマルチバイト文字がバイトオフセットをずらす）。ここは変えないこと。

---

## P4 — `validate_data_kubun` が毎レコード `strptime` を撃って捨てている

### 事実

`src/parser/status_domain.py:145-157`:

```python
if data_kubun in _current_values(record_type, context):
    not_before = CURRENT_DATA_KUBUN_NOT_BEFORE.get((record_type, data_kubun))
    explicit_make_date = _make_date(make_date)      # ← 常に実行
    if (not_before is not None and explicit_make_date is not None and ...):
```

`explicit_make_date` は `not_before is not None` のときしか使われない。
そして `CURRENT_DATA_KUBUN_NOT_BEFORE` の中身は
`{("UM", "9"): date(2003, 4, 22)}` の **1 件だけ**
（`src/parser/status_domain.py:90`）。

`_make_date` は `datetime.strptime(value, "%Y%m%d")` を呼ぶ。
`strptime` は locale 正規化と正規表現を通るため重い。

### 実測

```
validate_data_kubun (RA,'1') with make_date : 6.54 us/call
same, without make_date                     : 1.22 us/call
```

**5.3 µs/レコードが捨てられている。** `validate_fixed_record` から
全物理レコードで呼ばれ、オッズでは展開行ごとにも走る。RA の profile でも
`_strptime` が 5,001 回 / 0.088 秒 cumtime で出ている。

### 対処

`not_before is not None` を先に判定して短絡するだけ。挙動は完全に不変。
`_make_date` 自体も、8 桁 ASCII 数字なら
`date(int(v[:4]), int(v[4:6]), int(v[6:8]))` で足り、`strptime` は不要。

---

## P5 — `convert_record_types` がレコード不変の判定を毎フィールド繰り返す

### 事実

`src/importer/importer.py:7765-7929`。取り込み時間の約 40%。
フィールドループの中に、レコードが決まった時点で答えが確定している判定が
7 組並んでいる。

```python
for field_name, value in record.items():
    ...
    if (table_name in _HN_STORAGE_TABLES and field_name in _HN_BLANK_TEXT_FIELDS and ...):
    if (table_name in _ODDS_STORAGE_TABLES and field_name in _ODDS_BLANK_TEXT_FIELDS and ...):
    if (table_name in _H6_STORAGE_TABLES  and ...):
    if (table_name in _H1_STORAGE_TABLES  and ...):
    if (table_name in _UM_ERASE_STORAGE_TABLES and ...):
    if (table_name in _SK_STORAGE_TABLES  and ...):
```

`table_name in ...` は 1 レコード 1 回で足りるのに、
NL_RA の 123 フィールド × 7 = 861 回実行される。

INTEGER / REAL 枝のセンチネル判定も冗長（`src/importer/importer.py:7872-7878`）:

```python
str_value.startswith("***") or "****" in str_value or all(c in "-*" for c in str_value)
    or "--" in str_value or "*" in str_value
```

`"*" in str_value` が前 2 つを完全に包含する。`all(...)` の genexp は
profile 上 165,000 回 / 0.060 秒 cumtime で出ている。

### 実測（試作との比較）

テーブル単位で「空白許容フィールド集合」と「÷10 対象集合」を事前計算し、
冗長なセンチネル判定を落とした試作を同一入力で比較:

```
current convert_record_types: 49.3 us/rec
prototype (table-cached)    : 29.7 us/rec      -> 1.66x
identical output: True
```

NL_RA で出力は完全一致。試作は概念実証であり、CS / HN / ODDS / H1 / H6 /
UM / SK の各分岐を厳密に写したものではない。実装時は各分岐の
契約テストで担保すること。

### 対処

`table_name` → `(column_types, blank_text_fields, divide_by_10_fields)` を
返すメモ化ヘルパを 1 つ足し、ループ内は集合 1 回引きにする。
数字抽出の `"".join(c for c in s if c.isdigit() or c == "-")` は
`str.translate` + 事前計算テーブルに置き換えられる。

---

## P6 — PostgreSQL: `insert` / `insert_many` のたびに PK カタログ照会

### 事実

- `src/database/postgresql_handler.py:756`（`insert`）
- `src/database/postgresql_handler.py:816`（`insert_many`）

いずれも `self._get_primary_key_columns(table_name)` を毎回呼ぶ。中身は
`pg_index` × `pg_attribute` の JOIN（`src/database/postgresql_handler.py:126-133`）で、
**キャッシュがない**。

`insert_many` ではバッチごとに 1 往復で済むが、`insert` 経路では **1 行 1 往復**。
そして 1 行 `insert` を使う経路が 2 つある。

- `_flush_batch` のバッチ失敗フォールバック
  （`src/importer/importer.py:8955-8966`）— 1 行ごとに `insert` + `commit`
- リアルタイム更新の `_handle_new_record` / `_handle_update_record`
  （`src/realtime/updater.py:1388`, `1429`）— 1 レコードごとに `insert`

後者では 1 レコードにつき「カタログ照会 1 往復 + INSERT 1 往復」になる。

### 対処

テーブル名 → PK 列を接続単位でキャッシュし、DDL（`create_table` /
マイグレーション）で無効化する。PK はスキーマの性質で、レコードごとに
変わらない。

---

## P7 — PostgreSQL: 1 行 × 1 列ごとに関数内 import

`src/database/postgresql_handler.py:648-685`:

```python
@staticmethod
def _normalize_insert_value(table_name, column, value):
    try:
        from src.database.schema_types import get_column_type   # ← 列ごと
        column_type = get_column_type(table_name, column)
```

`_normalize_insert_data` が全列に対して呼ぶので、1,000 行 × 123 列 =
123,000 回の import 文実行 + 123,000 回の `get_column_type`。
`get_column_type` 自体はキャッシュ済みだが、`get_table_column_types(table_name)`
を**バッチで 1 回**引いて辞書を使い回せば呼び出しごと消える。

同種の in-loop import の実測コストは 0.24 µs/回（P13 参照）。

---

## P8 — PostgreSQL: バルクロード戦略

- `executemany` の pg8000 経路は 1 行ずつ `run()` する
  （`src/database/postgresql_handler.py:317-331`）。`insert_many` は
  多行 VALUES で回避しているが、他の `executemany` 呼び出しは回避されない。
- セットアップ取り込みで `COPY` を使っていない。`ON CONFLICT` が必要なので
  `COPY` を直接は使えないが、**一時テーブルへ `COPY` → `INSERT ... SELECT ...
  ON CONFLICT`** は定石で、多行 VALUES に対して桁が変わる。
  5 年分セットアップのような一括経路に限って導入する価値がある。
- `max_params = 30000`（`src/database/postgresql_handler.py:836`）は
  PostgreSQL のバインドパラメータ上限 65,535 に対して保守的。
  列数の多いテーブル（NL_RA は 123 列）では 1 文あたり 243 行に落ちる。
  上限を 60,000 程度に上げるだけで文数が半減する。

---

## P9 — 生データキャッシュが 1 レコード 1 open/close

### 事実

`src/cache/manager.py:118-124`:

```python
def write_nl_record(self, spec, date_str, raw):
    path = self._nl_path(spec, date_str)
    with self._lock_for(f"nl:{spec}:{date_str}"):
        with open(path, "ab") as f:        # ← レコードごとに open/close
            f.write(self.HEADER.pack(len(raw)))
            f.write(raw)
```

`HistoricalFetcher.fetch`（`src/fetcher/historical.py:411`）から
バッファごとに呼ばれる。

### 実測

```
open-per-record append: 10.8 us/rec
kept-open append      :  1.1 us/rec     -> 10x
```

これは Linux の tmpfs 上の数値である。**リリース検証済み環境は
Windows NTFS で、しかもウイルス対策ソフトが `CreateFile` ごとに介入する。
そちらでは差はこれより大きくなる。**

### 対処

`(spec, date)` ごとに開いたハンドルを保持し、fetch の `finally` で閉じる。
`checkpoint_nl` / `restore_nl` によるロールバック契約は、
truncate 前に `flush()` すれば保てる。

---

## P10 — CH / KS の結合テーブル検証がバッチごとに走る

`src/importer/importer.py:8707` と `8734`:

```python
verified_ch_result_table = verify_ch_coupled_table(self.database, table_name)
...
verified_ks_result_table = verify_ks_coupled_table(self.database, table_name)
```

`_flush_batch` の冒頭にあり、**キャッシュされていない**。中身は
`table_exists_strict` × 2 + `verify_table_schema` × 2 で、
`verify_table_schema` はカタログ照会に加えて `CREATE TABLE` 文の
正規表現解析を行う（`src/database/migration.py:421-470`）。

同じファイルの CK は `self._verified_ck_child_tables` でキャッシュしている
（`src/importer/importer.py:8724-8731`）。CH / KS だけ揃っていない。

対処: CK と同じ形にする。

---

## P11 — `resolve_standard_table_name` がレコードごとにカタログを叩く

`DataImporter._get_table_name`（`src/importer/importer.py:8149-8167`）は
`use_jravan_schema` が有効なとき、**レコードごとに**
`resolve_standard_table_name(self.database, table_name)` を呼ぶ。

この関数（`src/importer/importer.py:91-210`）は `NL_AV` / `NL_BT` /
`NL_JG` / `NL_JC` / `NL_TC` / `NL_WF` / `NL_SK` / `NL_BR` / `NL_HY` に
該当した場合、`database.table_exists()` を 2 回ずつ発行する。

これは「レガシー標準テーブルが残っていないか」というスキーマ形状の検査で、
1 回の取り込み中に変わらない。NL_SK を 10 万件取り込めばカタログ照会が
20 万回になる。

対処: `(native_table_name, transaction_generation)` でメモ化する。
該当しないレコード種別では文字列比較 10 回で済んでいるので、
コストは該当種別に限定される。

---

## P12 — fetch ループの 10 秒ごとの full `gc.collect()`

`src/fetcher/base.py:193-196`:

```python
current_time = time.time()
if (current_time - last_gc_time) >= 10.0:
    gc.collect()
```

COM の BSTR バッファが溜まって `E_UNEXPECTED` になる件の緩和策で、
根拠がある。**削除は勧めない。**

ただし full collection は全世代を走査するので、O6 スナップショットのように
数千の dict を保持している最中に当たると 1 回で数百 ms かかりうる。
検討に値するのは次の 2 つで、いずれも Windows + JV-Link 実機で
計測してからにすべきである。

- `gc.collect(1)`（第 2 世代を除く）で緩和目的を満たせるか
- そもそも `buff` への参照を明示的に切れば GC を強制せずに済むか
  （kmy-keiba の `Array.Resize(ref buff, 0)` に相当する処置）

---

## P13 — 個別に小さいが数が多いもの

| 箇所 | 内容 | 実測 |
| --- | --- | --- |
| `src/parser/base.py:222` | `_extract_field` の中で `from src.parser.converters import convert_value`。変換 1 回 0.546 µs に対し import 文が 0.24 µs（+44%）。ただし `convert_type` を使うのは CC / JC / TC / WE / RT_RC の 5 パーサのみなので絶対値は小さい。1 行動かすだけで消える。 | 0.24 µs/field |
| `src/importer/importer.py:5381` | `clean_record_metadata` が `metadata_fields` セットをレコードごとに構築。モジュール定数の `frozenset` にする。 | 0.225 µs/rec |
| `src/importer/importer.py:8203` | `_has_complete_primary_key` がレコードごとに `from src.database.table_mappings import JRAVAN_TO_JLTSQL`。 | — |
| `src/importer/importer.py:5200` | `_record_type_from_record` が毎回 tuple と set を組む。1 レコードあたり約 6 回呼ばれる。 | 0.97 µs × 6 = 5.8 µs/rec |
| `src/importer/importer.py:8322-8397` | 該当しない 18 個の `validate_*_record` を毎レコード呼ぶ。`record_type` → ハンドラの dispatch 表にすれば O(型数) が O(1) になる。 | 5.1 µs/rec |
| `src/database/base.py:249-258` | `insert_many` が毎バッチ全行を舐めて列の和集合を作り直す。異種行（O1 の馬行 vs 枠連行）のための正しい配慮だが、最初の行のキーで試して差異が出たときだけ和集合に切り替えれば同じ安全性で速い。 | — |
| `src/importer/importer.py` 全体 | 関数内 import が 167 か所。多くは循環参照回避で正当だが、ホットパス上のものはモジュール先頭に上げられる。 | — |
| `src/fetcher/base.py:219` | `to_date` フィルタが parse **後**に効く。範囲外レコードも全フィールド parse してから捨てる。ヘッダの `MakeDate` は固定オフセット（byte 3-11）にあるが、レコード日付（Year/MonthDay）は種別ごとに位置が違うため、安全に前倒しできるのは種別マップに無いレコードの早期スキップまで。 | — |

---

## 着手順の提案

計測済みの効果と、契約テストへの影響の小ささで並べる。

| 順 | 項目 | 期待効果 | リスク |
| --- | --- | --- | --- |
| 1 | P4: `not_before` 短絡 | 全レコード -5.3 µs。挙動不変 | ほぼ無し |
| 2 | P1-1: follower 判定をループ前半へ移動 | O1 -29%、O6 -222 ms/物理 | 小（判定の依存関係のみ確認） |
| 3 | P3: `decode_field` を 1 か所に集約し ASCII 優先化 | parse 2.4x | 小（ASCII 範囲は cp932 と同一） |
| 4 | P5: `convert_record_types` のテーブル単位事前計算 | 取り込み -1.66x（全体の 40% を占める部分） | 中（分岐ごとの契約テストで担保） |
| 5 | P9: キャッシュのハンドル保持 | キャッシュ有効時 -10 µs/レコード。Windows ではさらに大 | 小（rollback 契約に flush が必要） |
| 6 | P2: 二重検証の解消 | オッズ検証 -50% | 中（責務の切り分けを要設計） |
| 7 | P6/P7/P11/P10: カタログ照会のキャッシュ | PostgreSQL とリアルタイムで大 | 小〜中（無効化条件の設計） |
| 8 | P8: COPY 経由のバルクロード | セットアップ取り込みで桁が変わりうる | 大（別イテレーション） |
| 9 | P1-2: follower 行をそもそも生成しない | O6 の parse/メモリを 4,896 分の 1 に | 大（統計・契約テストに影響） |

1〜3 は挙動不変に近く、合わせると parse で約 2.4 倍、取り込みで
O6 系の最悪ケースが劇的に改善する。ここから始めるのが妥当と考える。

## 未検証・保留

- Windows + 32-bit Python + JV-Link COM 実機での計測。`JVRead` の往復と
  ダウンロード待ちが支配的な区間では、本レビューの改善が壁時計時間に
  どこまで効くかは実測しないと言えない。P12 は特に実機計測が必須。
- PostgreSQL 実接続での計測。P6〜P8 は静的解析に基づく指摘であり、
  往復レイテンシの実測値を持っていない。
- `src/services/realtime_monitor.py` と `src/realtime/monitor.py` は
  ポーリング周期が支配的と見られ、本レビューでは深く追っていない。
- `src/cache/s3_sync.py` の転送経路は未計測。

## 再現手順

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[dev]"
# 本レビューの計測スクリプトはリポジトリに含めていない。
# 上記の各節に、対象関数と入力の作り方を記載してある。
```
