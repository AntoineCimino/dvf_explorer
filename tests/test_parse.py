import csv
from datetime import date
from decimal import Decimal

import duckdb
import pytest

from src.parse import create_view, parse_file


@pytest.mark.parametrize(
    "filename,date_header,disposition_header,lot_header",
    [
        ("valeursfoncieres-2014.txt", "Date de mutation", "N° disposition", "1er lot"),
        ("valeursfoncieres-2017-s2.txt", "Date mutation", "No disposition", "1er lot"),
        ("valeursfoncieres-2020.txt", "Date mutation", "No disposition", "1er lot"),
        ("ValeursFoncieres-2024.txt", "Date mutation", "No disposition", "1er lot"),
    ],
)
def test_parse_known_header_variants_and_repeatably(tmp_path, filename, date_header,
                                                     disposition_header, lot_header):
    headers = [
        disposition_header, date_header, "Nature mutation", "Valeur fonciere",
        "Code departement", "Code commune", "Commune", "Prefixe de section",
        "Section", "No plan", lot_header, "Surface Carrez du 1er lot",
        "Nombre de lots", "Code type local", "Type local", "Surface reelle bati",
        "Nombre pieces principales", "Nature culture", "Nature culture speciale",
        "Surface terrain", "Identifiant de document", "Code service CH",
    ]
    source = tmp_path / filename
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="|")
        writer.writerow(headers)
        writer.writerow([
            "1", "12/03/2024", "Vente", "123456,78", "2A", "004", "Ajaccio",
            "000", "AB", "0123", "lot-1", "45,25", "1", "2", "Appartement",
            "45", "2", "", "", "0", "", "",
        ])

    first = parse_file(source, tmp_path / "out")
    first_bytes = [path.read_bytes() for path in first]
    second = parse_file(source, tmp_path / "out")
    assert [path.read_bytes() for path in second] == first_bytes
    assert len(first) == 1
    year = filename.split("-")[1][:4]
    assert f"millesime={year}/version=1/dept=2A" in first[0].as_posix()
    result = duckdb.connect().execute(
        "SELECT date_mutation, valeur_fonciere, insee_code FROM read_parquet(?)",
        [str(first[0])],
    ).fetchone()
    assert result == (date(2024, 3, 12), Decimal("123456.78"), "2A004")

    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="|")
        writer.writerow(headers)
        writer.writerow([
            "1", "12/03/2024", "Vente", "130000,00", "2A", "004", "Ajaccio",
            "000", "AB", "0123", "lot-1", "45,25", "1", "2", "Appartement",
            "45", "2", "", "", "0", "", "",
        ])
    parse_file(source, tmp_path / "out", version=2)
    con = create_view(tmp_path / "out")
    assert con.execute("SELECT DISTINCT valeur_fonciere FROM dvf").fetchall() == [(Decimal("130000.00"),)]
    con.close()


def test_unknown_header_fails_loudly(tmp_path):
    source = tmp_path / "valeursfoncieres-2024.txt"
    source.write_text("Mystery field|Date mutation\nfoo|12/03/2024\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown DVF header"):
        parse_file(source, tmp_path / "out")
