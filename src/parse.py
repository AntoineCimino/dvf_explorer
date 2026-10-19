"""Parse official DVF pipe-delimited files into deterministic Parquet partitions."""

from __future__ import annotations

import csv
from datetime import datetime
import os
import re
import shutil
import unicodedata
from pathlib import Path
import tempfile
from typing import Iterator

import duckdb
from src.sources import millesime_from_name


CANONICAL_COLUMNS = (
    "no_disposition", "date_mutation", "nature_mutation", "valeur_fonciere", "no_voie",
    "btq", "type_voie", "code_voie", "voie", "code_postal", "commune",
    "code_departement", "code_commune", "prefixe_section", "section",
    "no_plan", "no_volume", "lot_1", "lot_2", "lot_3", "lot_4",
    "lot_5", "carrez_1", "carrez_2", "carrez_3", "carrez_4", "carrez_5",
    "nombre_lots", "code_type_local", "type_local",
    "surface_reelle_bati", "nombre_pieces_principales", "code_nature_culture", "nature_culture",
    "nature_culture_speciale", "surface_terrain", "insee_code",
)


def _key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.strip().lower())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


_ALIASES = {
    "no_disposition": "no_disposition", "n_disposition": "no_disposition",
    "n_de_disposition": "no_disposition",
    "numero_disposition": "no_disposition",
    "date_mutation": "date_mutation", "date_de_mutation": "date_mutation",
    "nature_mutation": "nature_mutation",
    "valeur_fonciere": "valeur_fonciere", "no_voie": "no_voie",
    "n_de_voie": "no_voie",
    "btq": "btq", "b_t_q": "btq", "type_de_voie": "type_voie",
    "type_voie": "type_voie", "code_voie": "code_voie", "voie": "voie",
    "code_postal": "code_postal", "code_postal_du_bien": "code_postal",
    "commune": "commune", "code_departement": "code_departement",
    "code_commune": "code_commune", "prefixe_de_section": "prefixe_section",
    "prefixe_section": "prefixe_section", "section": "section",
    "no_plan": "no_plan", "n_plan": "no_plan", "numero_plan": "no_plan",
    "no_volume": "no_volume", "n_volume": "no_volume",
    "numero_volume": "no_volume", "nombre_de_lots": "nombre_lots",
    "nombre_lots": "nombre_lots", "code_type_local": "code_type_local",
    "type_local": "type_local", "surface_reelle_bati": "surface_reelle_bati",
    "nombre_pieces_principales": "nombre_pieces_principales",
    "code_nature_culture": "code_nature_culture",
    "nature_culture": "nature_culture", "nature_culture_speciale": "nature_culture_speciale",
    "surface_terrain": "surface_terrain",
}
for _index in range(1, 6):
    _ALIASES[f"{_index}er_lot"] = f"lot_{_index}"
    _ALIASES[f"{_index}eme_lot"] = f"lot_{_index}"
    _ALIASES[f"{_index}e_lot"] = f"lot_{_index}"
    _ALIASES[f"surface_carrez_du_{_index}er_lot"] = f"carrez_{_index}"
    _ALIASES[f"surface_carrez_du_{_index}eme_lot"] = f"carrez_{_index}"
    _ALIASES[f"surface_carrez_du_{_index}e_lot"] = f"carrez_{_index}"

# These source fields are intentionally omitted from the analytical schema.
# The document identifier is empty in published files; article references are
# legal annotations rather than transaction attributes.
_IGNORED_HEADERS = {
    "id_document", "identifiant_de_document", "code_service_ch",
    "reference_document", "1_articles_cgi", "2_articles_cgi",
    "3_articles_cgi", "4_articles_cgi", "5_articles_cgi",
    "identifiant_local", "id_local",
}
_NULL = {"", "nan", "null", "none"}


def _value(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return None if value.lower() in _NULL else value


def _insee(department: str | None, commune: str | None) -> str | None:
    if not department or not commune:
        return None
    dept, city = department.strip().upper(), commune.strip().zfill(3)
    if dept in {"2A", "2B"}:
        return dept + city
    if dept.startswith("97") and len(dept) == 3:
        return dept + city[-2:]
    return dept.zfill(2) + city


def _date(value: str | None) -> str | None:
    if value is None:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Invalid DVF date: {value!r}")


def _decimal(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", normalized):
        raise ValueError(f"Invalid DVF decimal: {value!r}")
    return normalized


def _normalise_row(row: dict[str, str], line_number: int) -> dict[str, str | None]:
    result: dict[str, str | None] = {column: None for column in CANONICAL_COLUMNS}
    for header, value in row.items():
        key = _key(header)
        if key in _IGNORED_HEADERS:
            continue
        canonical = _ALIASES.get(key)
        if canonical is None:
            raise ValueError(f"Unknown DVF header on line {line_number}: {header!r}")
        if result[canonical] is not None:
            raise ValueError(f"Duplicate DVF field {canonical!r} on line {line_number}")
        result[canonical] = _value(value)
    for column in ("valeur_fonciere", "surface_reelle_bati", "surface_terrain"):
        result[column] = _decimal(result[column])
    result["date_mutation"] = _date(result["date_mutation"])
    for column in ("nombre_lots", "nombre_pieces_principales"):
        value = result[column]
        if value is not None and not value.isdigit():
            raise ValueError(f"Invalid integer for {column}: {value!r} on line {line_number}")
    result["insee_code"] = _insee(result["code_departement"], result["code_commune"])
    return result


def _read_rows(source: Path) -> Iterator[dict[str, str | None]]:
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="|")
        if not reader.fieldnames:
            raise ValueError(f"DVF file has no header: {source}")
        seen: set[str] = set()
        for header in reader.fieldnames:
            key = _key(header)
            if key not in _IGNORED_HEADERS and key not in _ALIASES:
                raise ValueError(f"Unknown DVF header: {header!r}")
            if key in seen and key not in _IGNORED_HEADERS:
                raise ValueError(f"Duplicate DVF header: {header!r}")
            seen.add(key)
        for number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"Malformed pipe-delimited row at line {number}")
            yield _normalise_row(row, number)


def parse_file(
    source: Path,
    output_dir: Path,
    *,
    version: int = 1,
    row_group_size: int = 100_000,
) -> list[Path]:
    """Parse a complete DVF file to one deterministic Parquet per department.

    Rows are sorted by their full canonical representation before writing. The
    pinned DuckDB dependency, one thread, fixed row groups and zstd settings
    keep output reproducible for identical input bytes. Source versions are
    retained in separate partition trees.
    """
    source, output_dir = Path(source), Path(output_dir)
    if row_group_size < 1 or version < 1:
        raise ValueError("row_group_size must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    millesime = millesime_from_name(source.name)
    staging = Path(tempfile.mkdtemp(prefix=f".dvf-{millesime}-v{version}-", dir=output_dir))
    db_path = staging / "parse.duckdb"
    spill_dir = staging / "spill"
    spill_dir.mkdir()
    con = duckdb.connect(str(db_path))
    con.execute("SET threads=1")
    con.execute("SET preserve_insertion_order=true")
    memory_limit = os.environ.get("DVF_DUCKDB_MEMORY_LIMIT")
    if memory_limit:
        if not re.fullmatch(r"\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB)", memory_limit, re.I):
            raise ValueError("DVF_DUCKDB_MEMORY_LIMIT must be a size such as 3GB")
        con.execute(f"SET memory_limit = '{memory_limit}'")
    escaped_spill = spill_dir.as_posix().replace("'", "''")
    con.execute(f"SET temp_directory = '{escaped_spill}'")
    con.execute("CREATE TABLE dvf (" + ", ".join(
        f'"{column}" VARCHAR' for column in CANONICAL_COLUMNS
    ) + ")")
    placeholders = ",".join("?" for _ in CANONICAL_COLUMNS)
    batch = []
    con.execute("BEGIN TRANSACTION")
    try:
        for row in _read_rows(source):
            batch.append([row[column] for column in CANONICAL_COLUMNS])
            if len(batch) == 5_000:
                con.executemany(f"INSERT INTO dvf VALUES ({placeholders})", batch)
                batch.clear()
        if batch:
            con.executemany(f"INSERT INTO dvf VALUES ({placeholders})", batch)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        shutil.rmtree(staging, ignore_errors=True)
        raise
    outputs = []
    departments = [r[0] for r in con.execute(
        "SELECT DISTINCT code_departement FROM dvf WHERE code_departement IS NOT NULL ORDER BY 1"
    ).fetchall()]
    types = {
        "date_mutation": "DATE", "valeur_fonciere": "DECIMAL(18,2)",
        "surface_reelle_bati": "DECIMAL(12,2)", "surface_terrain": "DECIMAL(14,2)",
        "nombre_lots": "INTEGER", "nombre_pieces_principales": "INTEGER",
    }
    projection = ", ".join(
        f'CAST("{c}" AS {types[c]}) AS "{c}"' if c in types else f'"{c}"'
        for c in CANONICAL_COLUMNS
    )
    for department in departments:
        safe_dept = re.sub(r"[^A-Za-z0-9_-]", "_", department)
        target_dir = (staging / f"millesime={millesime}" / f"version={version}"
                      / f"dept={safe_dept}")
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / "part-00000.parquet"
        con.execute(
            f"COPY (SELECT {projection} FROM dvf WHERE code_departement=? "
            f"ORDER BY {', '.join(chr(34) + c + chr(34) for c in CANONICAL_COLUMNS)}) "
            f"TO '{target.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE {int(row_group_size)})",
            [department],
        )
        outputs.append(output_dir / f"millesime={millesime}" / f"version={version}"
                       / f"dept={safe_dept}" / target.name)
    con.close()
    db_path.unlink(missing_ok=True)
    (staging / "parse.duckdb.wal").unlink(missing_ok=True)
    shutil.rmtree(spill_dir, ignore_errors=True)
    staged_version = staging / f"millesime={millesime}" / f"version={version}"
    staged_version.mkdir(parents=True, exist_ok=True)
    target_version = output_dir / f"millesime={millesime}" / f"version={version}"
    target_version.parent.mkdir(parents=True, exist_ok=True)
    backup = target_version.with_name(f".version-{version}.previous")
    if backup.exists():
        shutil.rmtree(backup)
    if target_version.exists():
        os.replace(target_version, backup)
    try:
        os.replace(staged_version, target_version)
    except Exception:
        if backup.exists():
            os.replace(backup, target_version)
        raise
    if backup.exists():
        shutil.rmtree(backup)
    shutil.rmtree(staging, ignore_errors=True)
    return outputs


def create_view(parquet_root: Path, database: Path = Path(":memory:")) -> duckdb.DuckDBPyConnection:
    """Create a unified view over the latest snapshot for each millésime."""
    root = Path(parquet_root).resolve().as_posix().replace("'", "''")
    con = duckdb.connect(str(database))
    con.execute(f"""
        CREATE OR REPLACE VIEW dvf AS
        WITH snapshots AS (
            SELECT * FROM read_parquet('{root}/millesime=*/version=*/*/*.parquet',
                                       hive_partitioning=true, union_by_name=true)
        ), latest AS (
            SELECT millesime, max(CAST(version AS INTEGER)) AS version
            FROM snapshots GROUP BY millesime
        )
        SELECT s.* EXCLUDE (millesime, version, dept)
        FROM snapshots s JOIN latest l
          ON s.millesime = l.millesime AND CAST(s.version AS INTEGER) = l.version
    """)
    return con
