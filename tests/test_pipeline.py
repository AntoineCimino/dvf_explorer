import csv
from decimal import Decimal

import duckdb

from src.main import main
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
        "SELECT status FROM read_parquet(?)",
        [str(history / "millesime=2024/versions=1-2/row_history.parquet")],
    ).fetchone()
    assert saved == ("modified",)
    view = create_view(parquet)
    assert view.execute("SELECT valeur_fonciere FROM dvf").fetchone() == (Decimal("125000.00"),)
    view.close()
