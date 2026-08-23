#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PROTOTYPE — throwaway. Do not ship. Do not import from src/.

Answers one question from hayato1980/keibaai_cloud#280:

    insert_many を「1 行テンプレート + executemany」に置き換えると本当に速くなるか。
    (遅くなったら採らない、が受け入れ条件 3)

比較する 4 経路:

  A values_chunked   現行実装。src/database/postgresql_handler.py:779 の insert_many を
                     そのまま呼ぶ（本物の production コードを計測する）
  B executemany      候補実装。1 行テンプレート + self.executemany、dedupe あり
  C executemany_nodd 候補実装から _dedupe_rows_by_primary_key を外したもの
                     (executemany では「同一文で同じ conflict key を 2 回」制約が消えるため)
  D copy_temp        issue の第 2 案。TEMP 表へ COPY してから INSERT ... SELECT ... ON CONFLICT

計測するもの:
  - 実時間 (プロファイラなし)
  - psycopg のクエリ解析に消えた self 時間 (_split_query / _query2pg*_nocache) — issue の本丸
  - 戻り値       (現行は投入行数、base 実装は rowcount。ここが変わると回帰する)
  - 表の最終状態 (md5)。4 経路で一致しなければ採用できない

接続は scripts/setup_pg_test_db.py と同じ契約 (POSTGRES_* → PG* → 既定値)。
PGHOST にディレクトリを渡せば unix socket で繋がる。

  python scripts/PROTOTYPE_insert_many_bench.py --rows 200000
"""

import argparse
import cProfile
import os
import pstats
import random
import sys
import time
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.postgresql_handler import PostgreSQLDatabase  # noqa: E402
from src.database.schema import SCHEMAS  # noqa: E402

TABLE = "TS_O1"


# --------------------------------------------------------------------------
# 接続 (scripts/setup_pg_test_db.py と同じ契約)
# --------------------------------------------------------------------------
def _env(primary: str, fallback: str, default: str) -> str:
    return os.environ.get(primary) or os.environ.get(fallback) or default


def db_config() -> Dict[str, Any]:
    return {
        "host": _env("POSTGRES_HOST", "PGHOST", "localhost"),
        "port": int(_env("POSTGRES_PORT", "PGPORT", "5432")),
        "database": _env("POSTGRES_DB", "PGDATABASE", "proto"),
        "user": _env("POSTGRES_USER", "PGUSER", "postgres"),
        "password": os.environ.get("POSTGRES_PASSWORD") or os.environ.get("PGPASSWORD", ""),
        "sslmode": os.environ.get("PGSSLMODE", "prefer"),
        "connect_timeout": 5,
    }


# --------------------------------------------------------------------------
# データ生成 — TS_O1 の実形状 (30 列 / PK 9 列)。
# O1 は 1 レコードが「馬別行」と「枠連行」に展開されるので列が疎になる。
# PK 列は NOT NULL なので馬別行は Kumi='', 枠連行は Umaban=0 で埋まる前提。
# --------------------------------------------------------------------------
def make_rows(n: int, dup_rate: float, seed: int = 42) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    rows: List[Dict[str, Any]] = []
    race = 0
    while len(rows) < n:
        race += 1
        # レースキーは衝突させない。混ぜて桁上がりさせると PK 空間が小さくなり、
        # dedupe が効きすぎて「投入スループット」ではなく「重複削り」を測ってしまう。
        year = 2026
        racenum = race % 12 + 1
        jyocd = f"{(race // 12) % 10:02d}"
        nichiji = (race // 120) % 12 + 1
        kaiji = (race // 1440) % 6 + 1
        monthday = 101 + (race // 8640) % 300
        hasso = f"{9 + (race % 8):02d}{(race * 7) % 60:02d}"
        head = {
            "RecordSpec": "O1",
            "DataKubun": "1",
            "MakeDate": "20260823",
            "Year": year,
            "MonthDay": monthday,
            "JyoCD": jyocd,
            "Kaiji": kaiji,
            "Nichiji": nichiji,
            "RaceNum": racenum,
            "HassoTime": hasso,
            "TorokuTosu": 18,
            "SyussoTosu": 16,
            "CollectedAt": "2026-08-23T06:00:00",
        }
        # 馬別行 (単勝・複勝)
        for umaban in range(1, 17):
            row = dict(head)
            row.update({
                "TanFlag": "1", "FukuFlag": "1", "FukuChakubaraiKey": "3",
                "Umaban": umaban, "Kumi": "",
                "TanOdds": round(rng.uniform(1.2, 300.0), 1),
                "TanNinki": rng.randint(1, 16),
                "FukuUmaban": umaban,
                "FukuOddsLow": round(rng.uniform(1.0, 50.0), 1),
                "FukuOddsHigh": round(rng.uniform(1.0, 80.0), 1),
                "FukuNinki": rng.randint(1, 16),
                "TanVote": rng.randint(0, 90_000_000),
                "FukuVote": rng.randint(0, 90_000_000),
            })
            rows.append(row)
        # 枠連行
        for a in range(1, 9):
            for b in range(a, 9):
                row = dict(head)
                row.update({
                    "WakurenFlag": "1",
                    "Umaban": 0, "Kumi": f"{a}{b}",
                    "WakurenOdds": round(rng.uniform(1.5, 900.0), 1),
                    "WakurenNinki": rng.randint(1, 36),
                    "WakurenVote": rng.randint(0, 50_000_000),
                })
                rows.append(row)
    rows = rows[:n]
    # バッチ内 PK 重複 (dedupe が実在する理由)
    ndup = int(n * dup_rate)
    for _ in range(ndup):
        src = rng.randrange(len(rows))
        dup = dict(rows[src])
        dup["TanOdds"] = round(rng.uniform(1.2, 300.0), 1)
        rows.insert(rng.randrange(len(rows)), dup)
    return rows


# --------------------------------------------------------------------------
# B / C: 候補実装 — 1 行テンプレート + executemany
#    postgresql_handler.py:779 insert_many と同じ前処理、SQL の組み方だけ差し替え
# --------------------------------------------------------------------------
def insert_many_executemany(db, table_name, data_list, use_replace=True, dedupe=True) -> int:
    data_list = [db._normalize_insert_data(table_name, row) for row in data_list]

    columns: List[str] = []
    seen = set()
    for row in data_list:
        for column in row.keys():
            if column not in seen:
                columns.append(column)
                seen.add(column)
    quoted_columns = [db._quote_identifier(col) for col in columns]
    placeholders = ", ".join(["?" for _ in columns])

    if use_replace:
        pk_columns = db._get_primary_key_columns(table_name)
        if dedupe:
            data_list = db._dedupe_rows_by_primary_key(data_list, pk_columns)
        if pk_columns:
            update_columns = [c for c in quoted_columns if c.lower() not in pk_columns]
            pk_list = ", ".join(pk_columns)
            if update_columns:
                update_set = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_columns])
                conflict_sql = f" ON CONFLICT ({pk_list}) DO UPDATE SET {update_set}"
            else:
                conflict_sql = f" ON CONFLICT ({pk_list}) DO NOTHING"
        else:
            conflict_sql = " ON CONFLICT DO NOTHING"
    else:
        conflict_sql = ""

    sql = (
        f"INSERT INTO {table_name} ({', '.join(quoted_columns)}) "
        f"VALUES ({placeholders}){conflict_sql}"
    )
    parameter_rows = [tuple(row.get(col) for col in columns) for row in data_list]
    db.executemany(sql, parameter_rows)
    return len(data_list)


# --------------------------------------------------------------------------
# D: COPY → TEMP → INSERT ... SELECT ... ON CONFLICT
# --------------------------------------------------------------------------
def insert_many_copy(db, table_name, data_list, use_replace=True) -> int:
    data_list = [db._normalize_insert_data(table_name, row) for row in data_list]

    columns: List[str] = []
    seen = set()
    for row in data_list:
        for column in row.keys():
            if column not in seen:
                columns.append(column)
                seen.add(column)
    quoted_columns = [db._quote_identifier(col) for col in columns]
    pk_columns = db._get_primary_key_columns(table_name) if use_replace else []

    cur = db._cursor
    tmp = "proto_stage"
    cur.execute(f"DROP TABLE IF EXISTS {tmp}")
    cur.execute(
        f"CREATE TEMP TABLE {tmp} AS SELECT {', '.join(quoted_columns)} "
        f"FROM {table_name} WITH NO DATA"
    )
    copy_sql = f"COPY {tmp} ({', '.join(quoted_columns)}) FROM STDIN"
    with cur.copy(copy_sql) as cp:
        for row in data_list:
            cp.write_row(tuple(row.get(col) for col in columns))

    if pk_columns:
        update_columns = [c for c in quoted_columns if c.lower() not in pk_columns]
        pk_list = ", ".join(pk_columns)
        # 同一バッチ内の重複は DISTINCT ON + ctid DESC で「最後の行が勝つ」に揃える
        src = (
            f"SELECT DISTINCT ON ({pk_list}) {', '.join(quoted_columns)} "
            f"FROM {tmp} ORDER BY {pk_list}, ctid DESC"
        )
        if update_columns:
            update_set = ", ".join([f"{c} = EXCLUDED.{c}" for c in update_columns])
            conflict_sql = f" ON CONFLICT ({pk_list}) DO UPDATE SET {update_set}"
        else:
            conflict_sql = f" ON CONFLICT ({pk_list}) DO NOTHING"
    else:
        src = f"SELECT {', '.join(quoted_columns)} FROM {tmp}"
        conflict_sql = ""

    cur.execute(
        f"INSERT INTO {table_name} ({', '.join(quoted_columns)}) {src}{conflict_sql}"
    )
    n = cur.rowcount
    cur.execute(f"DROP TABLE IF EXISTS {tmp}")
    return n


VARIANTS = {
    "A values_chunked": lambda db, t, rows: db.insert_many(t, rows, use_replace=True),
    "B executemany": lambda db, t, rows: insert_many_executemany(db, t, rows, dedupe=True),
    "C executemany_nodedupe": lambda db, t, rows: insert_many_executemany(db, t, rows, dedupe=False),
    "D copy_temp": lambda db, t, rows: insert_many_copy(db, t, rows),
}

PARSE_FUNCS = ("_split_query", "_query2pg_nocache", "_query2pg_client_nocache")


# --------------------------------------------------------------------------
def reset_table(db, preload_rows=None):
    db._cursor.execute(f"TRUNCATE {TABLE}")
    db.commit()
    if preload_rows:
        # fixture の用意は計測対象外なので最速経路 (COPY) で流す
        insert_many_copy(db, TABLE, preload_rows, use_replace=True)
        db.commit()


def table_state(db) -> str:
    db._cursor.execute(
        f"SELECT count(*)::text || ':' || "
        f"coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '-') FROM {TABLE} t"
    )
    return list(db._cursor.fetchone().values())[0]


def parse_time(prof) -> float:
    st = pstats.Stats(prof)
    total = 0.0
    for (fn, _ln, name), (_cc, _nc, tt, _ct, _cs) in st.stats.items():
        if name in PARSE_FUNCS and "psycopg" in fn:
            total += tt
    return total


def run(scenario, db, rows, preload):
    print(f"\n{'='*78}\n### シナリオ: {scenario}\n{'='*78}")
    print(f"{'variant':<24} {'wall(s)':>9} {'解析(s)':>9} {'解析%':>7} {'戻り値':>10}  最終状態")
    print("-" * 78)
    baseline_state = None
    results = {}
    for name, fn in VARIANTS.items():
        reset_table(db, preload)
        t0 = time.perf_counter()
        ret = fn(db, TABLE, rows)
        db.commit()
        wall = time.perf_counter() - t0

        reset_table(db, preload)
        prof = cProfile.Profile()
        prof.enable()
        fn(db, TABLE, rows)
        prof.disable()
        db.commit()
        ptime = parse_time(prof)

        state = table_state(db)
        if baseline_state is None:
            baseline_state = state
        ok = "一致" if state == baseline_state else "★不一致"
        print(f"{name:<24} {wall:>9.2f} {ptime:>9.2f} {ptime/wall*100:>6.1f}% {ret:>10}  {ok}")
        results[name] = (wall, ptime, ret, state)
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=200_000)
    ap.add_argument("--dup-rate", type=float, default=0.02)
    args = ap.parse_args()

    print("PROTOTYPE — keibaai_cloud#280 / insert_many executemany 化の実測")
    import psycopg
    print(f"psycopg {psycopg.__version__} / libpq {psycopg.pq.version()} "
          f"/ has_pipeline={psycopg.capabilities.has_pipeline()}")

    rows = make_rows(args.rows, args.dup_rate)
    print(f"生成: {len(rows):,} 行 / {TABLE} 30 列 / PK 9 列 / バッチ内重複 {args.dup_rate:.0%}")

    cfg = db_config()
    print(f"接続: {cfg['host']}:{cfg['port']}/{cfg['database']}")
    db = PostgreSQLDatabase(cfg)
    db.connect()
    db._cursor.execute(f"DROP TABLE IF EXISTS {TABLE}")
    db._cursor.execute(SCHEMAS[TABLE])
    db.commit()
    print(f"chunk_size (現行) = 30000 // 30 = {30000 // 30} 行/文")

    run("全件 INSERT (空表から)", db, rows, preload=None)
    run("全件 ON CONFLICT DO UPDATE (同じ行を再投入)", db, rows, preload=rows)

    db._cursor.execute(f"DROP TABLE IF EXISTS {TABLE}")
    db.commit()
    db.disconnect()


if __name__ == "__main__":
    main()
