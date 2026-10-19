"""Build small year-scoped indexes and department Parquet files for the fronts."""

from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

import duckdb

from src.parse import CANONICAL_COLUMNS


SOURCE_URL = "https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres"
LICENSE = "Licence Ouverte 2.0"
CONTRACT_VERSION = "1.0"


def _write_json_gz(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as compressed:
            compressed.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    temporary.replace(path)


def _write_immutable_index(exports_root: Path, directory: str, payload: dict[str, str]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    relative = f"{directory}/index-{digest}.json"
    target = exports_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_bytes(encoded)
    return relative


def publish_raw_source(source: Path, exports_root: Path, *, year: int, version: int) -> str:
    """Retain a downloadable, reproducibly gzipped copy of source TXT bytes."""
    source, exports_root = Path(source), Path(exports_root)
    relative = f"sources/{year}/version={version}/{source.name}.gz"
    target = exports_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    with source.open("rb") as original, temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed:
            shutil.copyfileobj(original, compressed, length=1024 * 1024)
    temporary.replace(target)
    manifest_path = exports_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    snapshot = manifest.setdefault("snapshots", {}).setdefault(str(year), {})
    snapshot.update({"version": version, "raw_source": relative})
    history = manifest.setdefault("snapshot_history", {}).setdefault(str(year), [])
    for entry in history:
        if int(entry.get("version", -1)) == version:
            entry["raw_source"] = relative
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return relative


def _fetch_all(connection: duckdb.DuckDBPyConnection, query: str, parameters: list | None = None) -> list[dict[str, Any]]:
    cursor = connection.execute(query, parameters or [])
    names = [item[0] for item in cursor.description]
    rows: list[dict[str, Any]] = []
    while batch := cursor.fetchmany(10_000):
        rows.extend(dict(zip(names, row)) for row in batch)
    return rows


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        return float(value)
    return value


def _normalise_kpis(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: _json_value(value) for key, value in row.items()} for row in rows]


def _copy_parquet(connection: duckdb.DuckDBPyConnection, query: str, target: Path, parameters: list) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.unlink(missing_ok=True)
    escaped = temporary.resolve().as_posix().replace("'", "''")
    connection.execute(
        f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)",
        parameters,
    )
    temporary.replace(target)


def generate_year_exports(
    parquet_root: Path,
    exports_root: Path,
    *,
    year: int,
    version: int,
    source_name: str,
    source_sha256: str,
) -> dict[str, Any]:
    """Create a year bundle and merge its paths into exports/manifest.json."""
    parquet_root, exports_root = Path(parquet_root), Path(exports_root)
    if not parquet_root.exists():
        raise FileNotFoundError("Parsed DVF snapshots are missing")
    root = parquet_root.resolve().as_posix().replace("'", "''")
    exports_root.mkdir(parents=True, exist_ok=True)
    temporary_name = tempfile.mkdtemp(prefix=f"dvf-export-{year}-", dir=exports_root)
    spill_dir = Path(temporary_name) / "spill"
    spill_dir.mkdir()
    connection = duckdb.connect(str(Path(temporary_name) / "exports.duckdb"))
    connection.execute("SET threads=1")
    connection.execute("SET preserve_insertion_order=true")
    memory_limit = os.environ.get("DVF_DUCKDB_MEMORY_LIMIT")
    if memory_limit:
        if not re.fullmatch(r"\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB)", memory_limit, re.I):
            raise ValueError("DVF_DUCKDB_MEMORY_LIMIT must be a size such as 3GB")
        connection.execute(f"SET memory_limit = '{memory_limit}'")
    escaped_spill = spill_dir.as_posix().replace("'", "''")
    connection.execute(f"SET temp_directory = '{escaped_spill}'")
    connection.execute(f"""
        CREATE TEMP VIEW dvf_snapshots AS
        SELECT * FROM read_parquet(
          '{root}/millesime={year}/version={version}/dept=*/part-00000.parquet',
          hive_partitioning=true, union_by_name=true
        )
    """)

    missing_keys = connection.execute(
        "SELECT count(*) FROM dvf_snapshots WHERE CAST(millesime AS INTEGER)=? "
        "AND (date_mutation IS NULL OR insee_code IS NULL OR no_disposition IS NULL)",
        [year],
    ).fetchone()[0]
    if missing_keys:
        connection.close()
        shutil.rmtree(temporary_name, ignore_errors=True)
        raise ValueError(f"Cannot build mutation keys: {missing_keys} rows lack required fields")

    def normalized_text(column: str) -> str:
        value = (
            f"lower(regexp_replace(nfc_normalize(trim(coalesce(CAST({column} AS VARCHAR), ''))), "
            "'\\s+', ' ', 'g'))"
        )
        decimal = f"try_cast(replace({value}, ',', '.') AS DECIMAL(38,10))"
        decimal_text = f"regexp_replace(regexp_replace(CAST({decimal} AS VARCHAR), '0+$', ''), '\\.$', '')"
        return (
            f"CASE WHEN regexp_full_match({value}, '-?[0-9]+([,.][0-9]+)?') "
            f"THEN {decimal_text} ELSE {value} END"
        )

    key_columns = ("date_mutation", "insee_code", "no_disposition", "code_departement",
                   "prefixe_section", "section", "no_plan")
    key_payload = "to_json([" + ", ".join(
        normalized_text(f'"{column}"') for column in key_columns
    ) + "])"
    projection = ", ".join(f'"{column}"' for column in CANONICAL_COLUMNS)
    base_filter = "CAST(millesime AS INTEGER) = ? AND code_departement IS NOT NULL"
    result: dict[str, Any] = {"year": str(year), "details": {}, "files": []}
    try:
        depts = [row[0] for row in connection.execute(
            f"SELECT DISTINCT code_departement FROM dvf_snapshots WHERE {base_filter} ORDER BY 1",
            [year],
        ).fetchall()]
        for department in depts:
            safe_dept = "".join(char if char.isalnum() or char in "-_" else "_" for char in str(department))
            relative = f"details/{year}/version={version}/{safe_dept}.parquet"
            target = exports_root / relative
            query = (
                f"SELECT {projection}, sha256({key_payload}) AS mutation_key, "
                "CAST(NULL AS VARCHAR) AS status, CAST(NULL AS VARCHAR) AS flag, "
                "CAST(NULL AS DOUBLE) AS latitude, CAST(NULL AS DOUBLE) AS longitude "
                f"FROM dvf_snapshots WHERE {base_filter} AND dept=? AND code_departement=?"
            )
            _copy_parquet(connection, query, target, [year, department, department])
            result["details"][str(department)] = relative
            result["files"].append(relative)

        connection.execute(f"""
            CREATE OR REPLACE TEMP VIEW transactions AS
            SELECT date_mutation, no_disposition, insee_code, code_departement,
                   any_value(commune) AS commune, min(code_postal) AS code_postal,
                   max(valeur_fonciere) AS price,
                   sum(DISTINCT surface_reelle_bati) FILTER (WHERE surface_reelle_bati > 0) AS surface
            FROM dvf_snapshots
            WHERE CAST(millesime AS INTEGER) = {int(year)}
              AND code_departement IS NOT NULL AND date_mutation IS NOT NULL
              AND no_disposition IS NOT NULL
            GROUP BY date_mutation, no_disposition, insee_code, code_departement
        """)

        aggregate = """
            SELECT ?::INTEGER AS year, count(*)::BIGINT AS transaction_count,
                   median(price) AS median_price,
                   median(price / nullif(surface, 0)) AS median_price_per_m2,
                   quantile_cont(price / nullif(surface, 0), 0.25) AS p25_price_per_m2,
                   quantile_cont(price / nullif(surface, 0), 0.75) AS p75_price_per_m2,
                   median(surface) AS median_surface
            FROM transactions {where}
        """
        national = _fetch_all(connection, aggregate.format(where=""), [year])[0]
        national.update(commune="France", insee_code="FR", department="00")
        departments = _fetch_all(connection, """
            SELECT code_departement AS department, count(*)::BIGINT AS transaction_count,
                   median(price) AS median_price,
                   median(price / nullif(surface, 0)) AS median_price_per_m2,
                   quantile_cont(price / nullif(surface, 0), 0.25) AS p25_price_per_m2,
                   quantile_cont(price / nullif(surface, 0), 0.75) AS p75_price_per_m2,
                   median(surface) AS median_surface
            FROM transactions GROUP BY code_departement ORDER BY code_departement
        """)
        for row in departments:
            row["year"] = year
            row["commune"] = f"Département {row['department']}"
            row["insee_code"] = row["department"]
        communes = _fetch_all(connection, """
            SELECT commune, insee_code, min(code_postal) AS code_postal,
                   code_departement AS department, count(*)::BIGINT AS transaction_count,
                   median(price) AS median_price,
                   median(price / nullif(surface, 0)) AS median_price_per_m2,
                   quantile_cont(price / nullif(surface, 0), 0.25) AS p25_price_per_m2,
                   quantile_cont(price / nullif(surface, 0), 0.75) AS p75_price_per_m2,
                   median(surface) AS median_surface
            FROM transactions WHERE insee_code IS NOT NULL
            GROUP BY commune, insee_code, code_departement
            ORDER BY commune, insee_code
        """)
        for row in communes:
            row["year"] = year

        kpi_path = f"kpis/{year}.json.gz"
        _write_json_gz(exports_root / kpi_path, {
            "national": _normalise_kpis([national]),
            "departments": _normalise_kpis(departments),
            "communes": _normalise_kpis(communes),
        })
        result["kpis"] = kpi_path
        result["files"].append(kpi_path)

        places = _fetch_all(connection, """
            SELECT commune AS label, 'commune' AS kind, insee_code,
                   code_departement AS department, min(code_postal) AS code_postal,
                   NULL::VARCHAR AS section
            FROM dvf_snapshots
            WHERE CAST(millesime AS INTEGER)=? AND insee_code IS NOT NULL
            GROUP BY commune, insee_code, code_departement
            UNION ALL
            SELECT any_value(commune) || ' · section ' || coalesce(prefixe_section, '') || section AS label,
                   'section' AS kind, insee_code, code_departement AS department,
                   min(code_postal) AS code_postal, coalesce(prefixe_section, '') || section AS section
            FROM dvf_snapshots
            WHERE CAST(millesime AS INTEGER)=? AND insee_code IS NOT NULL AND section IS NOT NULL
            GROUP BY insee_code, code_departement, prefixe_section, section
            ORDER BY kind, label
        """, [year, year])
        search_path = f"search/{year}.json.gz"
        _write_json_gz(exports_root / search_path, {"places": places})
        result["search_index"] = search_path
        result["files"].append(search_path)

        manifest_path = exports_root / "manifest.json"
        manifest = {}
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.setdefault("kpi_files", {})[str(year)] = kpi_path
        manifest.setdefault("search_files", {})[str(year)] = search_path
        manifest.setdefault("departments", {})
        for department, relative in result["details"].items():
            manifest["departments"].setdefault(department, {}).setdefault("details", {})[str(year)] = relative
        manifest.setdefault("snapshots", {})[str(year)] = {
            "version": version,
            "source_name": source_name,
            "source_sha256": source_sha256,
            "details": result["details"],
        }
        versions = manifest.setdefault("snapshot_history", {}).setdefault(str(year), [])
        snapshot_entry = {
            "version": version,
            "source_name": source_name,
            "source_sha256": source_sha256,
            "details": result["details"],
        }
        versions[:] = [entry for entry in versions if int(entry.get("version", -1)) != version]
        versions.append(snapshot_entry)
        versions.sort(key=lambda entry: int(entry["version"]))
        kpi_index = _write_immutable_index(exports_root, "kpis", manifest["kpi_files"])
        search_index = _write_immutable_index(exports_root, "search", manifest["search_files"])
        manifest.update({
            "contract_version": CONTRACT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kpis": kpi_index,
            "search_index": search_index,
            "years": sorted(manifest["snapshots"], key=int),
            "source": {
                "name": "DGFiP — Demandes de valeurs foncières",
                "url": SOURCE_URL,
                "license": LICENSE,
            },
        })
        temporary = manifest_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(manifest_path)
        result["files"].extend([kpi_index, search_index, "manifest.json"])
        return result
    finally:
        connection.close()
        shutil.rmtree(temporary_name, ignore_errors=True)
