"""Batch processing utilities for JLTSQL.

This module provides utilities for batch processing of JV-Data.
"""

from datetime import datetime, timedelta
from typing import Generator, Iterator, List, Optional, Tuple

from src.database.base import BaseDatabase
from src.database.schema import create_all_tables
from src.fetcher.historical import HistoricalFetcher
from src.importer.importer import DataImporter, ImporterError
from src.utils.logger import get_logger
from src.utils.record_date import extract_record_year

logger = get_logger(__name__)

# JVOpen option that fetches an accumulated range in a single call. Such a run
# spans decades, so it commits per year instead of as one transaction.
SPLIT_SETUP_OPTION = 4


def _report_committed_year(year: int) -> None:
    """Announce a committed year on stdout.

    This marker is the only contract between jltsql and the backfill driver:
    the driver advances its resume point solely from the years reported here,
    so it never points at a year that was fetched but not committed.
    """
    print(f"[commit] year={year}", flush=True)


def _split_by_year(records: Iterator[dict]) -> Iterator[Tuple[dict, Iterator[dict]]]:
    """Split a record stream into groups that never span a year increase.

    Yields ``(state, group)`` pairs. Each group must be consumed before the
    next one is requested; once it is, ``state["year"]`` holds the year the
    group belongs to, or None when the group carried no dated record at all
    (the master data specs). Records with no date join the group around them,
    which is why no data-spec exclusion list is needed.

    A record whose year is *below* the group's year does not open a new group.
    Records are expected in ascending order, but a late arrival must not make
    the reported years go backwards — the driver would resume from the earlier
    year and re-fetch what is already committed.
    """
    records = iter(records)
    carried: List[dict] = []

    def group(state: dict) -> Generator[dict, None, None]:
        while True:
            if carried:
                record = carried.pop()
            else:
                try:
                    record = next(records)
                except StopIteration:
                    state["exhausted"] = True
                    return

            year = extract_record_year(record)
            if year is not None:
                if state["year"] is None:
                    state["year"] = year
                elif year > state["year"]:
                    carried.append(record)
                    return

            yield record

    while True:
        state: dict = {"year": None, "exhausted": False}
        group_records = group(state)
        yield state, group_records
        group_records.close()

        if state["exhausted"]:
            return
        if not carried:
            raise RuntimeError(
                "Year group was abandoned before the record stream advanced"
            )


class BatchProcessor:
    """Batch processor for JV-Data import.

    Coordinates fetching, parsing, and importing of JV-Data in batches.
    Fetches data from JV-Link starting from the specified date and filters
    records client-side based on the end date.

    Note:
        Service key must be configured in JRA-VAN DataLab application
        before using this class.

    Examples:
        >>> from src.database.sqlite_handler import SQLiteDatabase
        >>> db = SQLiteDatabase({"path": "./keiba.db"})
        >>> processor = BatchProcessor(database=db)
        >>> with db:
        ...     # Fetches from 20240601 onwards, imports records <= 20240630
        ...     processor.process_date_range(
        ...         data_spec="RACE",
        ...         from_date="20240601",
        ...         to_date="20240630",
        ...     )
    """

    def __init__(
        self,
        database: BaseDatabase,
        batch_size: int = 1000,
        sid: str = "UNKNOWN",
        service_key: Optional[str] = None,
        show_progress: bool = True,
        cache_manager=None,
    ):
        """Initialize batch processor.

        Args:
            database: Database handler instance
            batch_size: Records per batch
            sid: Session ID for JV-Link API (default: "UNKNOWN")
            service_key: Optional service key. If provided, it will be set
                        programmatically without requiring registry configuration.
            show_progress: Show stylish progress display (default: True)
            cache_manager: Optional CacheManager for local file cache read/write
        """
        self.fetcher = HistoricalFetcher(
            sid,
            service_key=service_key,
            show_progress=show_progress,
        )
        self.importer = DataImporter(database, batch_size)
        self.database = database
        self.cache_manager = cache_manager

        logger.info(
            "BatchProcessor initialized",
            sid=sid,
            has_service_key=service_key is not None,
            show_progress=show_progress,
        )

    def __del__(self):
        """Release JV-Link COM/bridge resources when processor is garbage-collected."""
        try:
            if hasattr(self.fetcher, 'jvlink') and hasattr(self.fetcher.jvlink, 'cleanup'):
                self.fetcher.jvlink.cleanup()
        except Exception:
            pass

    def process_date_range(
        self,
        data_spec: str,
        from_date: str,
        to_date: str,
        option: int = 1,
        auto_commit: bool = True,
        ensure_tables: bool = True,
    ) -> dict:
        """Process data for a date range.

        Args:
            data_spec: Data specification code
            from_date: Start date (YYYYMMDD)
            to_date: End date (YYYYMMDD) - records are filtered to this date
            option: JVOpen option:
                    1=通常データ（差分データ取得）
                    2=今週データ（直近のレースのみ）
                    3=セットアップ（全データ取得、ダイアログ表示）
                    4=分割セットアップ（初回のみダイアログ）
            auto_commit: Whether to auto-commit
            ensure_tables: Whether to ensure tables exist

        Returns:
            Dictionary with processing statistics

        Note:
            JV-Link fetches all data from from_date onwards, then filters
            records client-side to only import those with dates <= to_date.

            option=4 commits once per year of records instead of once for the
            whole data spec, and reports each committed year on stdout as
            ``[commit] year=YYYY``. A run interrupted partway keeps every year
            already committed.

        Examples:
            >>> processor = BatchProcessor(database=db)
            >>> stats = processor.process_date_range("RACE", "20240601", "20240630")
            >>> print(f"Imported {stats['records_imported']} records")
        """
        logger.info(
            "Starting batch processing",
            data_spec=data_spec,
            from_date=from_date,
            to_date=to_date,
            option=option,
        )

        if self._should_split_setup_range(from_date, to_date, option):
            return self._process_split_setup_range(
                data_spec=data_spec,
                from_date=from_date,
                to_date=to_date,
                option=option,
                auto_commit=auto_commit,
                ensure_tables=ensure_tables,
            )

        if self._should_commit_per_year(option, auto_commit):
            return self._process_year_boundary_range(
                data_spec=data_spec,
                from_date=from_date,
                to_date=to_date,
                option=option,
                ensure_tables=ensure_tables,
            )

        # Ensure tables exist
        if ensure_tables:
            logger.info("Ensuring all tables exist")
            create_all_tables(self.database)

        # Fetch and import records (use cache if available)
        try:
            if self.cache_manager:
                records = self.fetcher.fetch_with_cache(
                    self.cache_manager, data_spec, from_date, to_date, option
                )
            else:
                records = self.fetcher.fetch(data_spec, from_date, to_date, option)
            # Keep the whole data-spec import in one transaction. Committing
            # inside DataImporter would make a later parser/import rejection
            # impossible to roll back.
            begin_transaction = getattr(self.database, "begin_transaction", None)
            if begin_transaction is not None:
                begin_transaction()
            import_stats = self.importer.import_records(records, auto_commit=False)

            # Combine statistics
            fetch_stats = self.fetcher.get_statistics()
            combined_stats = {
                **fetch_stats,
                **import_stats,
                "records_failed": (
                    int(fetch_stats.get("records_failed", 0) or 0)
                    + int(import_stats.get("records_failed", 0) or 0)
                ),
            }

            failed_records = int(combined_stats.get("records_failed", 0) or 0)
            if failed_records:
                raise ImporterError(
                    f"Import rejected {failed_records} record(s)"
                )

            if auto_commit:
                self.database.commit()

            logger.info("Batch processing completed", **combined_stats)

            return combined_stats

        except Exception as e:
            try:
                self.database.rollback()
            except Exception as rollback_error:
                logger.warning(
                    "Batch rollback failed",
                    error=str(rollback_error),
                )
            logger.error("Batch processing failed", error=str(e))
            raise

    @staticmethod
    def _should_commit_per_year(option: int, auto_commit: bool) -> bool:
        # option=4 (分割セットアップ) は JVOpen 1回で数十年ぶんを流し込むため、
        # 全体を1トランザクションにすると途中で落ちたときに1行も残らない。
        # 年境界でコミットするかどうかは option から決まる性質であり、
        # 呼び出し側にフラグで指定させない。
        # auto_commit=False は「コミットは呼び出し側が持つ」という契約なので、
        # そのときは従来どおり単一トランザクションのまま扱う。
        return option == SPLIT_SETUP_OPTION and auto_commit

    def _process_year_boundary_range(
        self,
        data_spec: str,
        from_date: str,
        to_date: str,
        option: int,
        ensure_tables: bool,
    ) -> dict:
        """Import a setup range, committing once per year of records.

        Each year is its own transaction, so a run interrupted partway keeps
        every year that was already committed. A record rejection rolls back
        only the year it happened in.
        """
        logger.info(
            "Committing setup range at year boundaries",
            data_spec=data_spec,
            from_date=from_date,
            to_date=to_date,
            option=option,
        )

        if ensure_tables:
            logger.info("Ensuring all tables exist")
            create_all_tables(self.database)

        try:
            if self.cache_manager:
                records = self.fetcher.fetch_with_cache(
                    self.cache_manager, data_spec, from_date, to_date, option
                )
            else:
                records = self.fetcher.fetch(data_spec, from_date, to_date, option)

            import_totals: dict = {}
            fetch_failed_before = 0

            for state, year_records in _split_by_year(records):
                begin_transaction = getattr(self.database, "begin_transaction", None)
                if begin_transaction is not None:
                    begin_transaction()

                import_stats = self.importer.import_records(
                    year_records, auto_commit=False
                )

                # Fetch statistics are cumulative over the stream, so compare
                # against the previous year to see what this year rejected.
                fetch_failed_total = int(
                    self.fetcher.get_statistics().get("records_failed", 0) or 0
                )
                failed_records = (fetch_failed_total - fetch_failed_before) + int(
                    import_stats.get("records_failed", 0) or 0
                )
                fetch_failed_before = fetch_failed_total

                if failed_records:
                    raise ImporterError(
                        f"Import rejected {failed_records} record(s)"
                    )

                self.database.commit()

                year = state["year"]
                if year is not None:
                    _report_committed_year(year)
                    logger.info(
                        "Committed year",
                        data_spec=data_spec,
                        year=year,
                        **import_stats,
                    )

                for key, value in import_stats.items():
                    if isinstance(value, (int, float)):
                        import_totals[key] = import_totals.get(key, 0) + value
                    else:
                        import_totals[key] = value

            fetch_stats = self.fetcher.get_statistics()
            combined_stats = {
                **fetch_stats,
                **import_totals,
                "records_failed": (
                    int(fetch_stats.get("records_failed", 0) or 0)
                    + int(import_totals.get("records_failed", 0) or 0)
                ),
            }

            logger.info("Batch processing completed", **combined_stats)

            return combined_stats

        except Exception as e:
            try:
                self.database.rollback()
            except Exception as rollback_error:
                logger.warning(
                    "Batch rollback failed",
                    error=str(rollback_error),
                )
            logger.error("Batch processing failed", error=str(e))
            raise

    @staticmethod
    def _should_split_setup_range(from_date: str, to_date: str, option: int) -> bool:
        # option=4 (分割セットアップ) は JVOpen を1回だけ呼び出して全期間を一括取得する。
        # 年単位に分割すると各チャンクで JV-Link が fromtime 以降の全データを返すため
        # O(n^2) の処理量になる。option=3 のみ従来の年分割を維持する。
        if option != 3:
            return False
        start = datetime.strptime(from_date, "%Y%m%d")
        end = datetime.strptime(to_date, "%Y%m%d")
        return (end - start).days > 370

    def _iter_year_chunks(self, from_date: str, to_date: str) -> Iterator[Tuple[str, str]]:
        start = datetime.strptime(from_date, "%Y%m%d")
        end = datetime.strptime(to_date, "%Y%m%d")
        year = start.year
        while year <= end.year:
            chunk_start = max(start, datetime(year, 1, 1))
            chunk_end = min(end, datetime(year, 12, 31))
            yield chunk_start.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")
            year += 1

    def _process_split_setup_range(
        self,
        data_spec: str,
        from_date: str,
        to_date: str,
        option: int,
        auto_commit: bool,
        ensure_tables: bool,
    ) -> dict:
        logger.info(
            "Splitting setup range into yearly chunks to avoid JVOpen memory pressure",
            data_spec=data_spec,
            from_date=from_date,
            to_date=to_date,
            option=option,
        )
        if ensure_tables:
            create_all_tables(self.database)

        combined_stats: dict = {}
        try:
            begin_transaction = getattr(self.database, "begin_transaction", None)
            if begin_transaction is not None:
                begin_transaction()

            for idx, (chunk_from, chunk_to) in enumerate(
                self._iter_year_chunks(from_date, to_date), start=1
            ):
                logger.info(
                    "Processing setup chunk",
                    chunk_index=idx,
                    chunk_from=chunk_from,
                    chunk_to=chunk_to,
                    data_spec=data_spec,
                )
                chunk_stats = self.process_date_range(
                    data_spec=data_spec,
                    from_date=chunk_from,
                    to_date=chunk_to,
                    option=option,
                    auto_commit=False,
                    ensure_tables=False,
                )
                for key, value in chunk_stats.items():
                    if isinstance(value, (int, float)):
                        combined_stats[key] = combined_stats.get(key, 0) + value
                    else:
                        combined_stats[key] = value

            if auto_commit:
                self.database.commit()
            return combined_stats
        except Exception:
            try:
                self.database.rollback()
            except Exception as rollback_error:
                logger.warning(
                    "Split setup rollback failed",
                    error=str(rollback_error),
                )
            raise

    def process_month(
        self,
        year: int,
        month: int,
        data_spec: str = "RACE",
        option: int = 1,
        auto_commit: bool = True,
    ) -> dict:
        """Process data for a specific month.

        Args:
            year: Year (e.g., 2024)
            month: Month (1-12)
            data_spec: Data specification code
            auto_commit: Whether to auto-commit

        Returns:
            Dictionary with processing statistics

        Examples:
            >>> processor = BatchProcessor(database=db)
            >>> stats = processor.process_month(2024, 6, "RACE")
        """
        # Calculate date range
        start = datetime(year, month, 1)

        # Last day of month
        if month == 12:
            end = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end = datetime(year, month + 1, 1) - timedelta(days=1)

        from_date = start.strftime("%Y%m%d")
        to_date = end.strftime("%Y%m%d")

        logger.info(f"Processing month: {year}/{month:02d}")

        return self.process_date_range(data_spec, from_date, to_date, option=option, auto_commit=auto_commit)

    def process_year(
        self,
        year: int,
        data_spec: str = "RACE",
        option: int = 1,
        auto_commit: bool = True,
    ) -> dict:
        """Process data for a specific year.

        Args:
            year: Year (e.g., 2024)
            data_spec: Data specification code
            auto_commit: Whether to auto-commit

        Returns:
            Dictionary with processing statistics

        Examples:
            >>> processor = BatchProcessor(database=db)
            >>> stats = processor.process_year(2024, "RACE")
        """
        from_date = f"{year}0101"
        to_date = f"{year}1231"

        logger.info(f"Processing year: {year}")

        return self.process_date_range(data_spec, from_date, to_date, option=option, auto_commit=auto_commit)

    def process_multiple_specs(
        self,
        data_specs: List[str],
        from_date: str,
        to_date: str,
        auto_commit: bool = True,
    ) -> dict:
        """Process multiple data specifications.

        Args:
            data_specs: List of data specification codes
            from_date: Start date (YYYYMMDD)
            to_date: End date (YYYYMMDD)
            auto_commit: Whether to auto-commit

        Returns:
            Dictionary mapping data_spec to statistics

        Examples:
            >>> processor = BatchProcessor(database=db)
            >>> specs = ["RACE", "DIFF"]
            >>> results = processor.process_multiple_specs(
            ...     specs, "20240601", "20240630"
            ... )
        """
        results = {}
        successful_specs = []
        failed_specs = []

        for data_spec in data_specs:
            logger.info(f"Processing data spec: {data_spec}")

            try:
                stats = self.process_date_range(
                    data_spec=data_spec,
                    from_date=from_date,
                    to_date=to_date,
                    auto_commit=auto_commit,
                    ensure_tables=False,  # Only check once
                )
                results[data_spec] = stats
                successful_specs.append(data_spec)

            except Exception as e:
                logger.error(
                    f"Failed to process {data_spec}",
                    data_spec=data_spec,
                    error=str(e),
                )
                results[data_spec] = {"error": str(e)}
                failed_specs.append(data_spec)

        # Add partial success summary
        total_specs = len(data_specs)
        success_count = len(successful_specs)
        failure_count = len(failed_specs)

        results["_summary"] = {
            "total_specs": total_specs,
            "successful": success_count,
            "failed": failure_count,
            "success_rate": f"{success_count}/{total_specs}",
            "successful_specs": successful_specs,
            "failed_specs": failed_specs,
        }

        # Log partial success summary
        if failure_count > 0:
            logger.warning(
                f"Partial success: {success_count}/{total_specs} specs completed successfully",
                successful=success_count,
                failed=failure_count,
                successful_specs=successful_specs,
                failed_specs=failed_specs,
            )
        else:
            logger.info(
                f"All specs completed successfully: {success_count}/{total_specs}",
                successful_specs=successful_specs,
            )

        return results

    def get_combined_statistics(self) -> dict:
        """Get combined statistics from fetcher and importer.

        Returns:
            Dictionary with combined statistics
        """
        return {
            **self.fetcher.get_statistics(),
            **self.importer.get_statistics(),
        }

    def reset_statistics(self):
        """Reset all statistics."""
        self.fetcher.reset_statistics()
        self.importer.reset_statistics()
