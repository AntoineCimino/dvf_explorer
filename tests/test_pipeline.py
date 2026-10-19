import csv
from decimal import Decimal

import duckdb

from src.main import main
from src.exports import generate_year_exports
from src.keys import mutation_key
from src.parse import create_view


HEADERS = [
    "No disposition", "Date mutation", "Nature mutation", "Valeur fonciere",
    "Code departement", "Code commune", "Commune", "Prefixe de section",
    "Section", "No plan", "1er lot", "Surface Carrez du 1er lot",
    "Nombre de lots", "Code type local", "Type local", "Surface reelle bati",
    "Nombre pieces principales", "Code nature culture", "Nature culture",
    "Nature culture speciale", "Surface terrain",
]


def write_source(path, price):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="|")
        writer.writerow(HEADERS)
        writer.writerow([
            "1", "12/03/2024", "Vente", price, "75", "056", "Paris", "000",
            "AB", "0123", "lot-1", "45,25", "1", "2", "Appartement", "45",
            "2", "", "", "", "0",
        ])


def test_ingest_tracks_versions_and_preserves_history_without_private_paths(tmp_path):
    source = tmp_path / "valeursfoncieres-2024.txt"
    registry = tmp_path / "source_files.csv"
    parquet = tmp_path / "parquet"
    history = tmp_path / "row_history"
    write_source(source, "100000,00")
    args = [str(source), "--origin", "datagouv", "--registry", str(registry),
            "--parquet", str(parquet), "--history", str(history)]

    assert main(["ingest", *args]) == 0
    write_source(source, "125000,00")
    assert main(["ingest", *args]) == 0
    assert main(["ingest", *args]) == 0

    with registry.open(encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["version"] for row in rows] == ["1", "2"]
    assert str(tmp_path) not in registry.read_text(encoding="utf-8")
    saved = duckdb.connect().execute(
        "SELECT status, json_extract_string(changes, '$.valeur_fonciere.old') "
        "FROM read_parquet(?)",
        [str(history / "millesime=2024/versions=1-2/row_history.parquet")],
    ).fetchone()
    assert saved == ("modified", "100000.00")
    view = create_view(parquet)
    assert view.execute("SELECT valeur_fonciere FROM dvf").fetchone() == (Decimal("125000.00"),)
    view.close()


def test_year_export_contract_contains_source_attribution_and_department_details(tmp_path):
    source = tmp_path / "valeursfoncieres-2024.txt"
    write_source(source, "100000,00")
    registry = tmp_path / "source_files.csv"
    parquet = tmp_path / "parquet"
    exports = tmp_path / "exports"
    assert main(["ingest", str(source), "--origin", "datagouv", "--registry", str(registry), "--parquet", str(parquet)]) == 0
    with registry.open(encoding="utf-8") as stream:
        row = next(csv.DictReader(stream))

    result = generate_year_exports(
        parquet, exports, year=2024, version=1,
        source_name=row["name"], source_sha256=row["sha256"],
    )

    import gzip
    import json
    manifest = json.loads((exports / "manifest.json").read_text(encoding="utf-8"))
    kpis = json.loads(gzip.decompress((exports / manifest["kpi_files"]["2024"]).read_bytes()))
    assert manifest["source"]["url"].startswith("https://www.data.gouv.fr/datasets/")
    assert manifest["snapshots"]["2024"]["version"] == 1
    assert kpis["national"][0]["transaction_count"] == 1
    detail_path = exports / manifest["departments"]["75"]["details"]["2024"]
    result_row = duckdb.connect().execute(
        "SELECT mutation_key, latitude, status FROM read_parquet(?)", [str(detail_path)],
    ).fetchone()
    assert result_row[0]
    assert result_row[0] == mutation_key({
        "date_mutation": "2024-03-12", "insee_code": "75056", "no_disposition": "1",
        "code_departement": "75", "prefixe_section": "000", "section": "AB",
        "no_plan": "0123",
    })
    assert result_row[1:] == (None, None)
    assert result["files"][-1] == "manifest.json"
