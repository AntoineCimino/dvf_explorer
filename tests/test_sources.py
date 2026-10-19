from datetime import datetime, timezone
import hashlib

import pytest

from src.sources import read_registry, register_source


NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def test_registry_skips_identical_bytes_and_versions_changed_file(tmp_path):
    registry = tmp_path / "source_files.csv"
    source = tmp_path / "ValeursFoncieres-2017.txt"
    source.write_bytes(b"first publication\n")

    first = register_source(source, registry, origin="kdrive", fetched_at=NOW)
    assert first == {
        "name": source.name,
        "millesime": "2017",
        "version": "1",
        "sha256": hashlib.sha256(b"first publication\n").hexdigest(),
        "size": "18",
        "fetched_at": "2026-10-01T00:00:00+00:00",
        "origin": "kdrive",
        "url": "",
        "last_modified": "",
    }
    original_csv = registry.read_bytes()
    assert register_source(source, registry, origin="kdrive", fetched_at=NOW) is None
    assert registry.read_bytes() == original_csv

    second_source = tmp_path / "valeursfoncieres-2017-s2.txt"
    second_source.write_bytes(b"second publication\n")
    second = register_source(second_source, registry, origin="kdrive", fetched_at=NOW)
    assert second["version"] == "2"
    assert [row["version"] for row in read_registry(registry)] == ["1", "2"]


def test_different_year_starts_at_version_one(tmp_path):
    registry = tmp_path / "source_files.csv"
    for year in (2014, 2024):
        source = tmp_path / f"valeursfoncieres-{year}.txt"
        source.write_text(str(year))
        row = register_source(source, registry, origin="datagouv", fetched_at=NOW)
        assert row["version"] == "1"
        assert row["millesime"] == str(year)


def test_registry_rejects_private_url_and_unknown_filename(tmp_path):
    registry = tmp_path / "source_files.csv"
    source = tmp_path / "valeursfoncieres-2024.txt"
    source.write_bytes(b"data")
    with pytest.raises(ValueError, match="Private archive URLs"):
        register_source(source, registry, origin="kdrive", url="https://private.example/file")
    assert not registry.exists()

    source.rename(tmp_path / "unknown.txt")
    with pytest.raises(ValueError, match="Unrecognized DVF filename"):
        register_source(tmp_path / "unknown.txt", registry, origin="datagouv")
