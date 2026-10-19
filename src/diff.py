"""Multiset comparison for successive publications of one DVF millésime."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
import os
from pathlib import Path
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
