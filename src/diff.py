"""Multiset comparison for successive publications of one DVF millésime."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping

import duckdb

from src.keys import mutation_key, row_hash
from src.parse import CANONICAL_COLUMNS


def compare_versions(
    previous_rows: Iterable[Mapping[str, Any]],
    current_rows: Iterable[Mapping[str, Any]],
    *,
    previous_version: int,
    current_version: int,
    window_expired: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return row-level history events and counts for two complete snapshots.

    Duplicate rows are compared as a multiset. An old row paired with a new
    row for the same cadastral disposition becomes a modification; unmatched
    removals are retained and flagged according to whether the year left the
    source's publication window.
    """
    if current_version <= previous_version:
        raise ValueError("current_version must be greater than previous_version")
    old_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    new_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in previous_rows:
        snapshot = dict(row)
        old_groups[row_hash(snapshot)].append(snapshot)
    for row in current_rows:
        snapshot = dict(row)
        new_groups[row_hash(snapshot)].append(snapshot)

    events: list[dict[str, Any]] = []
    counts = Counter(added=0, removed=0, modified=0, unchanged=0)
    unmatched_old: list[dict[str, Any]] = []
    unmatched_new: list[dict[str, Any]] = []

    for digest in sorted(old_groups.keys() | new_groups.keys()):
        old = sorted(old_groups.get(digest, []), key=lambda r: str(r))
        new = sorted(new_groups.get(digest, []), key=lambda r: str(r))
        same = min(len(old), len(new))
        if same:
            events.append({
                "row_hash": digest,
                "mutation_key": mutation_key(new[0]),
                "first_seen_version": previous_version,
                "last_seen_version": current_version,
                "status": "unchanged",
                "flag": None,
                "count": same,
                "old_row": old[0],
                "new_row": new[0],
                "changes": {},
            })
            counts["unchanged"] += same
        unmatched_old.extend(old[same:])
        unmatched_new.extend(new[same:])

    old_by_mutation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    new_by_mutation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in unmatched_old:
        old_by_mutation[mutation_key(row)].append(row)
    for row in unmatched_new:
        new_by_mutation[mutation_key(row)].append(row)

    remaining_old, remaining_new = [], []
    for key in sorted(old_by_mutation.keys() | new_by_mutation.keys()):
        old = sorted(old_by_mutation.get(key, []), key=lambda r: (row_hash(r), str(r)))
        new = sorted(new_by_mutation.get(key, []), key=lambda r: (row_hash(r), str(r)))
        paired = min(len(old), len(new))
        for old_row, new_row in zip(old[:paired], new[:paired]):
            changes = {
                field: {"old": old_row.get(field), "new": new_row.get(field)}
                for field in sorted(old_row.keys() | new_row.keys())
                if old_row.get(field) != new_row.get(field)
            }
            events.append({
                "row_hash": row_hash(new_row),
                "mutation_key": key,
                "first_seen_version": previous_version,
                "last_seen_version": current_version,
                "status": "modified",
                "flag": None,
                "count": 1,
                "old_row": old_row,
                "new_row": new_row,
                "changes": changes,
            })
            counts["modified"] += 1
        remaining_old.extend(old[paired:])
        remaining_new.extend(new[paired:])

    for row in remaining_old:
        events.append({
            "row_hash": row_hash(row),
            "mutation_key": mutation_key(row),
            "first_seen_version": previous_version,
            "last_seen_version": previous_version,
            "status": "removed",
            "flag": "hors_fenetre" if window_expired else "retiree",
            "count": 1,
            "old_row": row,
            "new_row": None,
            "changes": {},
        })
        counts["removed"] += 1
    for row in remaining_new:
        events.append({
            "row_hash": row_hash(row),
            "mutation_key": mutation_key(row),
            "first_seen_version": current_version,
            "last_seen_version": current_version,
            "status": "added",
            "flag": None,
            "count": 1,
            "old_row": None,
            "new_row": row,
            "changes": {},
        })
        counts["added"] += 1

    events.sort(key=lambda event: (event["mutation_key"], event["status"], event["row_hash"]))
    return events, dict(counts)


def write_history_events(
    events: Iterable[Mapping[str, Any]],
    output_root: Path,
    *,
    millesime: int,
    previous_version: int,
    current_version: int,
) -> Path:
    """Write one immutable, queryable Parquet comparison partition."""
    target = (Path(output_root) / f"millesime={millesime}"
              / f"versions={previous_version}-{current_version}" / "row_history.parquet")
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(events, key=lambda event: (
        str(event["mutation_key"]), str(event["status"]), str(event["row_hash"]),
    ))
    connection = duckdb.connect()
    connection.execute("SET threads=1")
    connection.execute("""
        CREATE TABLE row_history (
            row_hash VARCHAR,
            mutation_key VARCHAR,
            first_seen_version INTEGER,
            last_seen_version INTEGER,
            status VARCHAR,
            flag VARCHAR,
            row_count INTEGER,
            old_row JSON,
            new_row JSON,
            changes JSON
        )
    """)
    connection.executemany(
        "INSERT INTO row_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(
            event["row_hash"], event["mutation_key"], event["first_seen_version"],
            event["last_seen_version"], event["status"], event["flag"], event["count"],
            json.dumps(event["old_row"], ensure_ascii=False, sort_keys=True, default=str),
            json.dumps(event["new_row"], ensure_ascii=False, sort_keys=True, default=str),
            json.dumps(event["changes"], ensure_ascii=False, sort_keys=True, default=str),
        ) for event in rows],
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".parquet", delete=False) as stream:
            temporary = Path(stream.name)
        temporary.unlink()
        output = temporary.resolve().as_posix().replace("'", "''")
        connection.execute(
            f"COPY (SELECT * FROM row_history ORDER BY mutation_key, status, row_hash) "
            f"TO '{output}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
        )
        os.replace(temporary, target)
    finally:
        connection.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return target


def create_history_view(history_root: Path, database: Path = Path(":memory:")) -> duckdb.DuckDBPyConnection:
    """Create a view over all retained comparison history partitions."""
    root = Path(history_root).resolve().as_posix().replace("'", "''")
    connection = duckdb.connect(str(database))
    connection.execute(
        f"CREATE OR REPLACE VIEW row_history AS "
        f"SELECT * FROM read_parquet('{root}/**/row_history.parquet', hive_partitioning=true)"
    )
    return connection


def read_snapshot_rows(parquet_root: Path, *, millesime: int, version: int) -> list[dict[str, Any]]:
    """Read one retained version, excluding Hive partition metadata from row identity."""
    version_root = Path(parquet_root) / f"millesime={millesime}" / f"version={version}"
    partition = version_root / "dept=*" / "*.parquet"
    if not list(version_root.glob("dept=*/part-*.parquet")):
        return []
    columns = ", ".join(f'"{column}"' for column in CANONICAL_COLUMNS)
    connection = duckdb.connect()
    cursor = connection.execute(
        f"SELECT {columns} FROM read_parquet(?, hive_partitioning=true, union_by_name=true)",
        [partition.as_posix()],
    )
    names = [description[0] for description in cursor.description]
    rows = []
    while batch := cursor.fetchmany(5_000):
        rows.extend(dict(zip(names, values)) for values in batch)
    connection.close()
    return rows


def compare_snapshot_files(
    previous_root: Path,
    current_root: Path,
    output_path: Path,
    *,
    previous_version: int,
    current_version: int,
) -> dict[str, int]:
    """Compare Parquet snapshots using DuckDB tables that spill to disk.

    Only changed rows are materialized in the returned history file; identical
    rows are counted in the summary. This avoids holding entire national
    snapshots as Python dictionaries during scheduled refreshes.
    """
    previous_root, current_root, output_path = map(Path, (previous_root, current_root, output_path))
    if current_version <= previous_version:
        raise ValueError("current_version must be greater than previous_version")
    if not list(previous_root.glob("dept=*/part-*.parquet")) or not list(current_root.glob("dept=*/part-*.parquet")):
        raise FileNotFoundError("Both previous and current snapshot Parquet partitions are required")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dvf-compare-", dir=output_path.parent) as temporary_name:
        temporary_root = Path(temporary_name)
        connection = duckdb.connect(str(temporary_root / "compare.duckdb"))
        connection.execute("SET threads=1")
        memory_limit = os.environ.get("DVF_DUCKDB_MEMORY_LIMIT")
        if memory_limit:
            if not re.fullmatch(r"\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB)", memory_limit, re.I):
                raise ValueError("DVF_DUCKDB_MEMORY_LIMIT must be a size such as 3GB")
            connection.execute(f"SET memory_limit = '{memory_limit}'")
        spill_dir = (temporary_root / "spill").as_posix().replace("'", "''")
        connection.execute(f"SET temp_directory = '{spill_dir}'")
        connection.execute("SET preserve_insertion_order=true")

        def hashed(values):
            return row_hash(dict(zip(CANONICAL_COLUMNS, values)))

        def keyed(values):
            try:
                return mutation_key(dict(zip(CANONICAL_COLUMNS, values)))
            except ValueError:
                return None

        list_type = duckdb.list_type(duckdb.sqltypes.VARCHAR)
        connection.create_function("dvf_row_hash", hashed, [list_type], duckdb.sqltypes.VARCHAR, null_handling="special")
        connection.create_function("dvf_mutation_key", keyed, [list_type], duckdb.sqltypes.VARCHAR, null_handling="special")
        values = "[" + ", ".join(f'CAST("{name}" AS VARCHAR)' for name in CANONICAL_COLUMNS) + "]"
        columns = ", ".join(f'"{name}"' for name in CANONICAL_COLUMNS)
        prev_glob = (previous_root / "dept=*" / "part-*.parquet").as_posix()
        curr_glob = (current_root / "dept=*" / "part-*.parquet").as_posix()
        try:
            for table, glob in (("old_rows", prev_glob), ("new_rows", curr_glob)):
                connection.execute(
                    f"CREATE TABLE {table} AS SELECT {columns}, "
                    f"dvf_row_hash({values}) AS row_hash, dvf_mutation_key({values}) AS mutation_key "
                    f"FROM read_parquet(?, hive_partitioning=true, union_by_name=true)",
                    [glob],
                )
                connection.execute(
                    f"CREATE TABLE {table}_counts AS SELECT row_hash, count(*)::BIGINT AS occurrences "
                    f"FROM {table} GROUP BY row_hash"
                )
            connection.execute("""
                CREATE TABLE old_delta AS
                SELECT * EXCLUDE (hash_rank, current_count) FROM (
                    SELECT old_rows.*, row_number() OVER (PARTITION BY old_rows.row_hash ORDER BY old_rows.row_hash) hash_rank,
                           coalesce(new_counts.occurrences, 0) current_count
                    FROM old_rows LEFT JOIN new_rows_counts new_counts USING (row_hash)
                ) WHERE hash_rank > current_count
            """)
            connection.execute("""
                CREATE TABLE new_delta AS
                SELECT * EXCLUDE (hash_rank, previous_count) FROM (
                    SELECT new_rows.*, row_number() OVER (PARTITION BY new_rows.row_hash ORDER BY new_rows.row_hash) hash_rank,
                           coalesce(old_counts.occurrences, 0) previous_count
                    FROM new_rows LEFT JOIN old_rows_counts old_counts USING (row_hash)
                ) WHERE hash_rank > previous_count
            """)
            connection.execute("""
                CREATE TABLE old_ranked AS
                SELECT old_delta.*,
                       row_number() OVER (PARTITION BY mutation_key ORDER BY row_hash) AS mutation_rank,
                       coalesce(new_key_counts.occurrences, 0) AS new_key_count
                FROM old_delta LEFT JOIN (
                    SELECT mutation_key, count(*)::BIGINT AS occurrences FROM new_delta
                    WHERE mutation_key IS NOT NULL GROUP BY mutation_key
                ) new_key_counts USING (mutation_key)
            """)
            connection.execute("""
                CREATE TABLE new_ranked AS
                SELECT new_delta.*,
                       row_number() OVER (PARTITION BY mutation_key ORDER BY row_hash) AS mutation_rank,
                       coalesce(old_key_counts.occurrences, 0) AS old_key_count
                FROM new_delta LEFT JOIN (
                    SELECT mutation_key, count(*)::BIGINT AS occurrences FROM old_delta
                    WHERE mutation_key IS NOT NULL GROUP BY mutation_key
                ) old_key_counts USING (mutation_key)
            """)
            old_json = "to_json(struct_pack(" + ", ".join(f'"{name}" := o."{name}"' for name in CANONICAL_COLUMNS) + "))"
            new_json = "to_json(struct_pack(" + ", ".join(f'"{name}" := n."{name}"' for name in CANONICAL_COLUMNS) + "))"
            changes = "to_json(map_from_entries(list_filter([" + ", ".join(
                "struct_pack(k := CASE WHEN o.\"{0}\" IS DISTINCT FROM n.\"{0}\" THEN '{0}' ELSE NULL END, "
                "v := json_object('old', CAST(o.\"{0}\" AS VARCHAR), 'new', CAST(n.\"{0}\" AS VARCHAR)))".format(name)
                for name in CANONICAL_COLUMNS
            ) + "], entry -> entry.k IS NOT NULL)))"
            connection.execute(f"""
                CREATE TABLE pair_events AS
                SELECT n.row_hash, n.mutation_key, {previous_version} AS first_seen_version,
                       {current_version} AS last_seen_version, 'modified' AS status,
                       NULL::VARCHAR AS flag, 1::INTEGER AS row_count,
                       {old_json} AS old_row, {new_json} AS new_row, {changes} AS changes
                FROM old_ranked o JOIN new_ranked n
                  ON o.mutation_key=n.mutation_key AND o.mutation_rank=n.mutation_rank
                WHERE o.mutation_key IS NOT NULL AND o.mutation_rank <= o.new_key_count
            """)
            connection.execute(f"""
                CREATE TABLE events AS
                SELECT * FROM pair_events
                UNION ALL
                SELECT row_hash, mutation_key, {previous_version}, {previous_version},
                       'removed', 'retiree', 1, {old_json}, NULL::JSON, '{{}}'::JSON
                FROM old_ranked o
                WHERE mutation_key IS NULL OR mutation_rank > new_key_count
                UNION ALL
                SELECT row_hash, mutation_key, {current_version}, {current_version},
                       'added', NULL::VARCHAR, 1, NULL::JSON, {new_json}, '{{}}'::JSON
                FROM new_ranked n
                WHERE mutation_key IS NULL OR mutation_rank > old_key_count
            """)
            temporary_output = output_path.with_name(f".{output_path.name}.tmp")
            temporary_output.unlink(missing_ok=True)
            target = temporary_output.resolve().as_posix().replace("'", "''")
            connection.execute(
                f"COPY (SELECT * FROM events ORDER BY mutation_key, status, row_hash) "
                f"TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)"
            )
            temporary_output.replace(output_path)
            unchanged = connection.execute("""
                SELECT coalesce(sum(least(old_rows_counts.occurrences, new_rows_counts.occurrences)), 0)
                FROM old_rows_counts JOIN new_rows_counts USING (row_hash)
            """).fetchone()[0]
            counts = {row[0]: int(row[1]) for row in connection.execute(
                "SELECT status, count(*) FROM events GROUP BY status"
            ).fetchall()}
            counts["unchanged"] = int(unchanged)
            for status in ("added", "removed", "modified", "unchanged"):
                counts.setdefault(status, 0)
            return counts
        finally:
            connection.close()
