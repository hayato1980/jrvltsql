"""All table-creation paths run the same strict storage verification.

Invariant: every table named in a ``STRICT_*_STORAGE_TABLES`` set is checked by
its ``verify_*_storage_schema`` function on every path that creates tables
(``SchemaManager.create_table``, ``SchemaManager.create_all_tables`` and the
module-level ``create_all_tables``). A path that skips a set silently leaves the
storage contract unenforced for that record type.
"""

import re
from pathlib import Path
from typing import Callable, Dict, List, Set, Tuple

import pytest

import src.database.schema as schema
import src.importer.importer as importer
from src.database.sqlite_handler import SQLiteDatabase

_SET_NAME = re.compile(r"^STRICT_([A-Z0-9]+)_STORAGE_TABLES$")


def _strict_sets() -> Dict[str, frozenset]:
    return {
        match.group(1).lower(): value
        for name, value in vars(schema).items()
        if (match := _SET_NAME.match(name))
    }


def _record_verifiers(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[str, str]]:
    calls: List[Tuple[str, str]] = []
    for key in _strict_sets():
        verifier_name = f"verify_{key}_storage_schema"

        def record(_db, table_name, *_args, _key=key, **_kwargs):
            calls.append((_key, table_name))
            return True

        monkeypatch.setattr(importer, verifier_name, record)
    return calls


def _via_schema_manager_create_table(db: SQLiteDatabase) -> None:
    manager = schema.SchemaManager(db)
    for table_name in schema.SCHEMAS:
        manager.create_table(table_name)


def _via_schema_manager_create_all_tables(db: SQLiteDatabase) -> None:
    schema.SchemaManager(db).create_all_tables()


def _via_module_create_all_tables(db: SQLiteDatabase) -> None:
    schema.create_all_tables(db)


CREATION_PATHS: Dict[str, Callable[[SQLiteDatabase], None]] = {
    "SchemaManager.create_table": _via_schema_manager_create_table,
    "SchemaManager.create_all_tables": _via_schema_manager_create_all_tables,
    "module create_all_tables": _via_module_create_all_tables,
}


def test_strict_sets_are_discovered() -> None:
    assert {"h6", "odds"} <= set(_strict_sets())


@pytest.mark.parametrize("path_name", CREATION_PATHS)
def test_every_strict_table_is_verified_on_every_creation_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_name: str,
) -> None:
    calls = _record_verifiers(monkeypatch)
    database = SQLiteDatabase({"path": str(tmp_path / "parity.db")})
    with database:
        CREATION_PATHS[path_name](database)

    verified: Set[Tuple[str, str]] = set(calls)
    missing = sorted(
        (key, table_name)
        for key, tables in _strict_sets().items()
        for table_name in tables
        if table_name in schema.SCHEMAS and (key, table_name) not in verified
    )
    assert missing == [], f"{path_name} skipped strict verification for {missing}"
