"""Test-side helpers for driving :class:`DataImporter`.

`DataImporter.import_single_record` used to be a 435-line second implementation
of the batch path, kept alive only by these tests. It is gone; `import_records`
is the single entry point. `import_one` keeps the one thing the tests actually
wanted from it — "import exactly this record and tell me whether it landed" —
on top of `import_records`.

`import_single_record` returned True whenever it handled the record without
counting a failure — including the paths that deliberately added nothing to
`records_imported`, such as a physical erase or a follower row folded into an
existing snapshot. `import_one` keeps that contract by watching `records_failed`
rather than `records_imported`. Statistics are cumulative across calls, so it is
measured as a delta.
"""

from src.importer.importer import DataImporter


def import_one(importer: DataImporter, record: dict, **kwargs) -> bool:
    """Import a single record through `import_records`.

    Returns True when the call added no failure, mirroring the boolean the
    removed `import_single_record` returned.
    """
    before = importer.get_statistics()["records_failed"]
    importer.import_records(iter([record]), **kwargs)
    return importer.get_statistics()["records_failed"] == before
