"""Discover and prepare the public parcel geolocation companion dataset."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import duckdb


GEOGRAPHY_DATASET_API = "https://www.data.gouv.fr/api/1/datasets/demandes-de-valeurs-foncieres-geolocalisees/"
GEOGRAPHY_DATASET_URL = "https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres-geolocalisees"
GEOGRAPHY_USER_AGENT = "dvf-explorer/0.1 (public geography refresh)"


@dataclass(frozen=True)
class GeographyPublication:
    year: int
    period: str
    name: str
    title: str
    url: str
    resource_id: str
    last_modified: str
    checksum_type: str
    checksum_value: str
    filesize: int | None


def _resource_period(title: str) -> tuple[int, str] | None:
    match = re.fullmatch(
        r"\s*DVF\s+(20\d{2})(?:\s*\((1er|2nd|1st|2nd)\s+semestre\))?\s*",
        title,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    year = int(match.group(1))
    semester = (match.group(2) or "").casefold()
    suffix = "-S1" if semester in {"1er", "1st"} else "-S2" if semester else ""
    return year, f"{year}{suffix}"


def discover_geography_publications(api_url: str = GEOGRAPHY_DATASET_API) -> list[GeographyPublication]:
    request = Request(api_url, headers={"User-Agent": GEOGRAPHY_USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=45) as response:
        payload = json.load(response)
    resources = payload.get("resources")
    if not isinstance(resources, list):
        raise ValueError("Geolocation dataset API response has no resource list")

    found: dict[int, GeographyPublication] = {}
    for resource in resources:
        if not isinstance(resource, dict) or str(resource.get("format", "")).casefold() != "csv.gz":
            continue
        title = str(resource.get("title") or "")
        period = _resource_period(title)
        if not period:
            continue
        year, period_name = period
        url = str(resource.get("url") or "")
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname or not (
            parts.hostname == "data.gouv.fr" or parts.hostname.endswith(".data.gouv.fr")
        ):
            raise ValueError("Unexpected host in geolocation resource metadata")
        checksum = resource.get("checksum") or {}
        publication = GeographyPublication(
            year=year,
            period=period_name,
            name=Path(parts.path).name,
            title=title,
            url=url,
            resource_id=str(resource.get("id") or ""),
            last_modified=str(resource.get("last_modified") or ""),
            checksum_type=str(checksum.get("type") or "").casefold(),
            checksum_value=str(checksum.get("value") or "").casefold(),
            filesize=int(resource["filesize"]) if resource.get("filesize") is not None else None,
        )
        current = found.get(year)
        if current is None or publication.last_modified > current.last_modified:
            found[year] = publication
    return [found[year] for year in sorted(found, reverse=True)]


def download_geography_publication(publication: GeographyPublication, target: Path) -> tuple[str, int]:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.download")
    request = Request(publication.url, headers={"User-Agent": GEOGRAPHY_USER_AGENT})
    sha256 = hashlib.sha256()
    expected_digest = (
        hashlib.new(publication.checksum_type)
        if publication.checksum_type in {"sha1", "sha256"} and publication.checksum_value
        else None
    )
    size = 0
    try:
        with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
            final_host = urlsplit(response.geturl()).hostname or ""
            if not (final_host == "data.gouv.fr" or final_host.endswith(".data.gouv.fr")):
                raise ValueError("Geolocation resource redirected outside data.gouv.fr")
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                sha256.update(chunk)
                if expected_digest:
                    expected_digest.update(chunk)
                size += len(chunk)
        if publication.filesize is not None and size != publication.filesize:
            raise ValueError("Downloaded geolocation resource size does not match the dataset metadata")
        if expected_digest and expected_digest.hexdigest() != publication.checksum_value:
            raise ValueError("Downloaded geolocation resource checksum does not match the dataset metadata")
        temporary.replace(target)
        return sha256.hexdigest(), size
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def build_geography_lookup(
    source_path: Path,
    output_dir: Path,
    parquet_root: Path,
    *,
    year: int,
) -> dict:
    """Write unique department parcel lookups and report raw-row match coverage."""
    source_path = Path(source_path).resolve()
    output_dir = Path(output_dir)
    parquet_root = Path(parquet_root).resolve()
    version_dirs = list((parquet_root / f"millesime={year}").glob("version=*"))
    version_dirs = [path for path in version_dirs if path.is_dir() and path.name.partition("=")[2].isdigit()]
    if not version_dirs:
        raise FileNotFoundError(f"No parsed DVF partitions are available for {year}")
    latest_version = max(int(path.name.partition("=")[2]) for path in version_dirs)
    raw_glob = parquet_root / f"millesime={year}" / f"version={latest_version}" / "dept=*" / "part-00000.parquet"
    raw_files = list(parquet_root.glob(f"millesime={year}/version={latest_version}/dept=*/part-00000.parquet"))
    if not raw_files:
        raise FileNotFoundError(f"No parsed DVF partitions are available for {year}")

    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f"dvf-geography-{year}-", dir=output_dir))
    connection = duckdb.connect(str(work / "geography.duckdb"))
    connection.execute("SET threads=1")
    connection.execute("SET preserve_insertion_order=true")
    memory_limit = os.environ.get("DVF_DUCKDB_MEMORY_LIMIT")
    if memory_limit:
        if not re.fullmatch(r"\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB)", memory_limit, re.I):
            raise ValueError("DVF_DUCKDB_MEMORY_LIMIT must be a size such as 3GB")
        connection.execute(f"SET memory_limit = '{memory_limit}'")
    escaped_source = source_path.as_posix().replace("'", "''")
    escaped_raw = raw_glob.as_posix().replace("'", "''")
    escaped_spill = (work / "spill").as_posix().replace("'", "''")
    (work / "spill").mkdir()
    connection.execute(f"SET temp_directory = '{escaped_spill}'")
    try:
        connection.execute(f"""
            CREATE TEMP TABLE geolocation_rows AS
            SELECT
              try_cast(date_mutation AS DATE) AS date_mutation,
              lpad(trim(numero_disposition), 6, '0') AS no_disposition,
              trim(code_departement) AS department,
              coalesce(nullif(trim(ancien_id_parcelle), ''), nullif(trim(id_parcelle), '')) AS parcel_key,
              try_cast(longitude AS DOUBLE) AS longitude,
              try_cast(latitude AS DOUBLE) AS latitude
            FROM read_csv_auto('{escaped_source}', header=true, all_varchar=true,
                               delim=',', quote='"', escape='"', strict_mode=false,
                               null_padding=true)
        """)
        connection.execute("""
            CREATE TEMP TABLE geography_keys AS
            SELECT date_mutation, no_disposition, department, parcel_key,
                   min(longitude) AS longitude, min(latitude) AS latitude
            FROM geolocation_rows
            WHERE date_mutation IS NOT NULL AND no_disposition <> '000000'
              AND department <> '' AND parcel_key IS NOT NULL
              AND longitude BETWEEN -180 AND 180 AND latitude BETWEEN -90 AND 90
            GROUP BY date_mutation, no_disposition, department, parcel_key
            HAVING count(DISTINCT (longitude, latitude)) = 1
        """)
        coverage = connection.execute(f"""
            WITH raw AS (
              SELECT date_mutation, no_disposition, code_departement,
                     CASE WHEN no_plan IS NOT NULL AND section IS NOT NULL
                          THEN insee_code
                            || lpad(coalesce(nullif(prefixe_section, ''), '0'), 3, '0')
                            || lpad(section, 2, '0')
                            || lpad(no_plan, 4, '0')
                     END AS parcel_key
              FROM read_parquet('{escaped_raw}', hive_partitioning=true, union_by_name=true)
              WHERE extract(year FROM date_mutation) = {int(year)}
            )
            SELECT count(*)::BIGINT AS total_rows,
                   count(*) FILTER (WHERE raw.parcel_key IS NOT NULL)::BIGINT AS rows_with_parcel,
                   count(*) FILTER (WHERE geography_keys.parcel_key IS NOT NULL)::BIGINT AS rows_with_coordinates
            FROM raw LEFT JOIN geography_keys
              ON raw.date_mutation = geography_keys.date_mutation
             AND lpad(raw.no_disposition, 6, '0') = geography_keys.no_disposition
             AND lpad(raw.code_departement, 3, '0') = lpad(geography_keys.department, 3, '0')
             AND raw.parcel_key = geography_keys.parcel_key
        """).fetchone()
        total_rows, rows_with_parcel, rows_with_coordinates = map(int, coverage)
        departments = connection.execute("SELECT DISTINCT department FROM geography_keys ORDER BY department").fetchall()
        details: dict[str, str] = {}
        for (department,) in departments:
            if not re.fullmatch(r"[0-9A-Za-z]{1,3}", str(department)):
                continue
            relative = f"{department}.parquet"
            target = output_dir / relative
            temporary = target.with_name(f".{target.name}.tmp")
            escaped_target = temporary.resolve().as_posix().replace("'", "''")
            connection.execute(f"""
                COPY (
                  SELECT date_mutation, no_disposition, department, parcel_key, latitude, longitude
                  FROM geography_keys WHERE department = ?
                ) TO '{escaped_target}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000)
            """, [department])
            temporary.replace(target)
            details[str(department)] = relative
        return {
            "total_rows": total_rows,
            "rows_with_parcel": rows_with_parcel,
            "rows_with_coordinates": rows_with_coordinates,
            "coverage_rate": rows_with_coordinates / total_rows if total_rows else 0.0,
            "details": details,
        }
    finally:
        connection.close()
        shutil.rmtree(work, ignore_errors=True)
