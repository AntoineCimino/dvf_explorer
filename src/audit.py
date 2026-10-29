"""Independent source-to-Parquet checks for one DVF snapshot."""

from __future__ import annotations

import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import duckdb


def _header_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")


def _department(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip().upper()
    if value in {"2A", "2B"}:
        return value
    return value.zfill(2)


def audit_snapshot(
    source: Path, parquet_root: Path, *, year: int, version: int,
    registry_sha256: str | None = None,
) -> dict:
    """Compare raw-record counts and department coverage with one parsed snapshot.

    This deliberately reads the original delimited source with Python's CSV
    reader, independently of the DuckDB parser used to create Parquet.
    """
    source = Path(source)
    snapshot = Path(parquet_root) / f"millesime={year}" / f"version={version}"
    partitions = sorted(snapshot.glob("dept=*/part-*.parquet"))
    if not source.is_file():
        raise FileNotFoundError(source)
    if not partitions:
        raise FileNotFoundError(f"No Parquet department partitions in {snapshot}")

    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)

    raw_departments: Counter[str] = Counter()
    source_rows = 0
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="|")
        if not reader.fieldnames:
            raise ValueError("Source has no header")
        department_header = next(
            (name for name in reader.fieldnames if _header_key(name) == "code_departement"), None
        )
        if department_header is None:
            raise ValueError("Source has no Code departement column")
        for row in reader:
            source_rows += 1
            department = _department(row.get(department_header))
            if department:
                raw_departments[department] += 1

    con = duckdb.connect()
    try:
        parquet_glob = (snapshot / "dept=*" / "part-*.parquet").resolve().as_posix()
        columns = [row[0] for row in con.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [parquet_glob]
        ).fetchall()]
        row_struct = ", ".join(
            f'"{column}" := "{column}"' for column in columns
        )
        parquet_rows, distinct_rows = con.execute(
            f"SELECT count(*), count(DISTINCT to_json(struct_pack({row_struct}))) "
            "FROM read_parquet(?)", [parquet_glob],
        ).fetchone()
        parquet_departments = {
            _department(department): int(count)
            for department, count in con.execute(
                "SELECT code_departement, count(*) FROM read_parquet(?) "
                "GROUP BY code_departement", [parquet_glob],
            ).fetchall()
            if department is not None
        }
        min_date, max_date = con.execute(
            "SELECT min(date_mutation), max(date_mutation) FROM read_parquet(?)", [parquet_glob]
        ).fetchone()
    finally:
        con.close()

    failures = []
    source_sha256 = digest.hexdigest()
    if source_rows != parquet_rows:
        failures.append("source_parquet_row_count_mismatch")
    if raw_departments != parquet_departments:
        failures.append("department_row_count_mismatch")
    if registry_sha256 is not None and source_sha256 != registry_sha256:
        failures.append("source_registry_sha256_mismatch")
    if min_date is not None and (min_date.year != year or max_date.year != year):
        failures.append("mutation_date_outside_expected_millesime")

    return {
        "audit_schema_version": 1,
        "source": {
            "name": source.name, "sha256": source_sha256,
            "registry_sha256": registry_sha256, "size_bytes": size,
        },
        "snapshot": {"millesime": year, "version": version},
        "checks": {
            "source_rows": source_rows,
            "parquet_rows": int(parquet_rows),
            "exact_duplicate_rows_in_parquet": int(parquet_rows - distinct_rows),
            "source_rows_by_department": dict(sorted(raw_departments.items())),
            "parquet_rows_by_department": dict(sorted(parquet_departments.items())),
            "mutation_date_min": min_date.isoformat() if min_date else None,
            "mutation_date_max": max_date.isoformat() if max_date else None,
        },
        "result": "fail" if failures else "pass",
        "failures": failures,
    }


def write_audit(report: dict, destination: Path | None = None) -> str:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if destination is not None:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(encoded, encoding="utf-8")
    return encoded
