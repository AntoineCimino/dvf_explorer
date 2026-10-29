import csv
import hashlib
import json

from src.audit import audit_snapshot
from src.main import main
from src.parse import parse_file
from src.sources import register_source


def _source(path, rows=1):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, delimiter="|")
        writer.writerow(["Date mutation", "Valeur fonciere", "Code departement", "Code commune"])
        for index in range(rows):
            writer.writerow(["12/03/2024", f"{100 + index},00", "75", "056"])


def test_audit_passes_when_raw_rows_match_parquet_and_registry(tmp_path):
    source = tmp_path / "valeursfoncieres-2024.txt"
    _source(source, rows=2)
    registry = tmp_path / "source_files.csv"
    metadata = register_source(source, registry, origin="datagouv")
    parquet = tmp_path / "parquet"
    parse_file(source, parquet)

    report = audit_snapshot(
        source, parquet, year=2024, version=1, registry_sha256=metadata["sha256"],
    )

    assert report["result"] == "pass"
    assert report["checks"]["source_rows"] == report["checks"]["parquet_rows"] == 2
    assert report["checks"]["source_rows_by_department"] == {"75": 2}
    assert report["checks"]["parquet_rows_by_department"] == {"75": 2}


def test_audit_fails_when_raw_source_no_longer_matches_parquet(tmp_path):
    source = tmp_path / "valeursfoncieres-2024.txt"
    _source(source)
    parquet = tmp_path / "parquet"
    parse_file(source, parquet)
    _source(source, rows=2)

    report = audit_snapshot(source, parquet, year=2024, version=1)

    assert report["result"] == "fail"
    assert "source_parquet_row_count_mismatch" in report["failures"]


def test_audit_cli_checks_registry_and_published_manifest_hashes(tmp_path):
    source = tmp_path / "valeursfoncieres-2024.txt"
    _source(source)
    registry = tmp_path / "source_files.csv"
    metadata = register_source(source, registry, origin="datagouv")
    parquet = tmp_path / "parquet"
    parse_file(source, parquet)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "snapshots": {"2024": {"version": 1, "source_sha256": metadata["sha256"]}},
    }), encoding="utf-8")
    report_path = tmp_path / "audit.json"

    result = main([
        "audit", str(source), "--year", "2024", "--version", "1",
        "--registry", str(registry), "--parquet", str(parquet),
        "--manifest", str(manifest), "--output", str(report_path),
    ])

    assert result == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["source"]["manifest_sha256"] == metadata["sha256"]
    assert report["result"] == "pass"


def test_public_auditor_can_use_manifest_without_private_registry(tmp_path):
    source = tmp_path / "valeursfoncieres-2024.txt"
    _source(source)
    parquet = tmp_path / "parquet"
    parse_file(source, parquet)
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "snapshots": {"2024": {"version": 1, "source_sha256": checksum}},
    }), encoding="utf-8")
    report_path = tmp_path / "audit.json"

    result = main([
        "audit", str(source), "--year", "2024", "--version", "1",
        "--registry", str(tmp_path / "not-present.csv"),
        "--parquet", str(parquet), "--manifest", str(manifest),
        "--output", str(report_path),
    ])

    assert result == 0
    assert json.loads(report_path.read_text(encoding="utf-8"))["result"] == "pass"
