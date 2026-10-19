import zipfile

from src.import_archive import collect_sources


def test_collect_sources_from_archive_and_sort_semester_versions(tmp_path):
    archive_path = tmp_path / "historical.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("2017/ValeursFoncieres-2017-s2.txt", b"second")
        archive.writestr("2017/valeursfoncieres-2017.txt", b"first")
        archive.writestr("2017/readme.txt", b"not a DVF publication")
        archive.writestr("../valeursfoncieres-2018.txt", b"future")

    files = collect_sources(archive_path, tmp_path / "staged")

    assert [path.name.lower() for path in files] == [
        "valeursfoncieres-2017.txt",
        "valeursfoncieres-2017-s2.txt",
        "valeursfoncieres-2018.txt",
    ]
    assert [path.read_bytes() for path in files] == [b"first", b"second", b"future"]
    assert not (tmp_path / "future").exists()
