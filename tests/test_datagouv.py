import hashlib
from io import BytesIO
import json
from unittest.mock import patch
import zipfile

import pytest

from src.datagouv import Publication, discover_publications, download_publication


def test_discovery_selects_only_current_dvf_transaction_resources():
    payload = {"resources": [
        {
            "id": "resource-2026", "title": "Valeurs foncières 2026 - Premier semestre",
            "url": "https://static.data.gouv.fr/resources/dvf/valeursfoncieres-2026-s1.txt.zip",
            "format": "txt.zip", "filesize": 100,
            "checksum": {"type": "sha1", "value": "abc"},
            "last_modified": "2026-10-12T17:16:52Z",
        },
        {
            "id": "documentation", "title": "Notice descriptive des fichiers de valeurs foncières",
            "url": "https://static.data.gouv.fr/resources/dvf/notice.pdf", "format": "pdf",
        },
    ]}
    response = BytesIO(json.dumps(payload).encode())
    with patch("src.datagouv.urlopen", return_value=response):
        publications = discover_publications("https://www.data.gouv.fr/api/test")

    assert len(publications) == 1
    assert publications[0].name == "valeursfoncieres-2026-s1.txt"
    assert publications[0].millesime == 2026
    assert publications[0].registry_url.endswith("valeursfoncieres-2026-s1.txt.zip")


def test_discovery_rejects_resource_urls_outside_datagouv():
    payload = {"resources": [{
        "title": "Valeurs foncières 2026", "url": "https://attacker.example/data/valeursfoncieres-2026.txt.zip",
    }]}
    with patch("src.datagouv.urlopen", return_value=BytesIO(json.dumps(payload).encode())):
        with pytest.raises(ValueError, match="Unexpected host"):
            discover_publications("https://www.data.gouv.fr/api/test")


def test_download_verifies_zip_and_extracts_only_expected_txt(tmp_path):
    text = b"No disposition|Date mutation\n1|01/01/2026\n"
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("folder/valeursfoncieres-2026-s1.txt", text)
        archive.writestr("../outside.txt", b"ignored")
    body = archive_buffer.getvalue()
    publication = Publication(
        name="valeursfoncieres-2026-s1.txt", title="Valeurs foncières 2026 - S1",
        url="https://static.data.gouv.fr/file.zip", resource_id="r1",
        last_modified="", checksum_type="sha1", checksum_value=hashlib.sha1(body).hexdigest(),
        filesize=len(body),
    )

    class Response(BytesIO):
        def geturl(self):
            return publication.url

    with patch("src.datagouv.urlopen", return_value=Response(body)):
        result = download_publication(publication, tmp_path)

    assert result.name.lower() == "valeursfoncieres-2026-s1.txt"
    assert result.read_bytes() == text
    assert sorted(path.name for path in tmp_path.iterdir()) == [result.name]
