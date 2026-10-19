"""Discover and download DVF publications through the data.gouv.fr API."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
import warnings
import zipfile

from src.sources import millesime_from_name


DATASET_API = "https://www.data.gouv.fr/api/1/datasets/demandes-de-valeurs-foncieres/"
USER_AGENT = "dvf-explorer/0.1 (public data refresh)"
_FILE = re.compile(r"valeursfoncieres[-_](20\d{2})(?:[-_]s([12]))?\.txt(?:\.zip)?$", re.I)


@dataclass(frozen=True)
class Publication:
    name: str
    title: str
    url: str
    resource_id: str
    last_modified: str
    checksum_type: str
    checksum_value: str
    filesize: int | None

    @property
    def millesime(self) -> int:
        return millesime_from_name(self.name)

    @property
    def registry_url(self) -> str:
        parts = urlsplit(self.url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def _safe_public_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("DVF resource URL must use HTTPS")
    host = parts.hostname.lower()
    if host != "data.gouv.fr" and not host.endswith(".data.gouv.fr"):
        raise ValueError("Unexpected host in data.gouv.fr resource metadata")
    return value


def _name_for_resource(resource: dict) -> str | None:
    url = str(resource.get("url") or "")
    base = Path(urlsplit(url).path).name
    match = _FILE.fullmatch(base)
    if match:
        return base[:-4] if base.lower().endswith(".zip") else base
    title = str(resource.get("title") or "")
    year = re.search(r"\b(20\d{2})\b", title)
    if not year or "valeur" not in title.casefold() or "fonci" not in title.casefold():
        return None
    semester = re.search(r"\b(?:s|semestre\s*)([12])\b", title, re.I)
    suffix = f"-s{semester.group(1)}" if semester else ""
    return f"valeursfoncieres-{year.group(1)}{suffix}.txt"


def discover_publications(api_url: str = DATASET_API) -> list[Publication]:
    """Return the current transaction-file resources, newest first by year."""
    request = Request(api_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(request, timeout=45) as response:
        payload = json.load(response)
    resources = payload.get("resources")
    if not isinstance(resources, list):
        raise ValueError("Dataset API response has no resource list")

    publications: list[Publication] = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        name = _name_for_resource(resource)
        if not name:
            continue
        url = _safe_public_url(str(resource.get("url") or ""))
        checksum = resource.get("checksum") or {}
        publications.append(Publication(
            name=name,
            title=str(resource.get("title") or name),
            url=url,
            resource_id=str(resource.get("id") or ""),
            last_modified=str(resource.get("last_modified") or ""),
            checksum_type=str(checksum.get("type") or "").lower(),
            checksum_value=str(checksum.get("value") or "").lower(),
            filesize=int(resource["filesize"]) if resource.get("filesize") is not None else None,
        ))

    # A dataset can briefly contain duplicate resources during replacement.
    # Keep its newest metadata record for each source filename.
    newest: dict[str, Publication] = {}
    for publication in publications:
        old = newest.get(publication.name.casefold())
        if old is None or publication.last_modified > old.last_modified:
            newest[publication.name.casefold()] = publication
    return sorted(newest.values(), key=lambda item: (item.millesime, item.name.casefold()), reverse=True)


def download_publication(publication: Publication, raw_dir: Path) -> Path:
    """Download, checksum, and safely extract one official TXT ZIP."""
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    request = Request(publication.url, headers={"User-Agent": USER_AGENT})
    zip_path: Path | None = None
    try:
        with urlopen(request, timeout=90) as response:
            _safe_public_url(response.geturl())
            with tempfile.NamedTemporaryFile(dir=raw_dir, suffix=".download", delete=False) as out:
                zip_path = Path(out.name)
                digest = hashlib.new(publication.checksum_type) if publication.checksum_type in {"sha1", "sha256"} else None
                size = 0
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
                    size += len(chunk)
                    if digest:
                        digest.update(chunk)
        if publication.filesize is not None and size != publication.filesize:
            warnings.warn(f"Published size hint differs for {publication.name}; validating the archive directly.")
        if digest and publication.checksum_value and digest.hexdigest() != publication.checksum_value:
            warnings.warn(f"Published checksum hint differs for {publication.name}; using the downloaded TXT SHA-256.")

        with zipfile.ZipFile(zip_path) as archive:
            candidates = []
            for item in archive.infolist():
                if item.is_dir() or not item.filename.lower().endswith(".txt"):
                    continue
                name = Path(item.filename.replace("\\", "/")).name
                try:
                    year = millesime_from_name(name)
                except ValueError:
                    continue
                if year == publication.millesime:
                    candidates.append((item, name))
            if len(candidates) != 1:
                raise ValueError(f"Expected one DVF TXT for {publication.name}; found {len(candidates)}")
            member, source_name = candidates[0]
            target = raw_dir / source_name
            with archive.open(member) as input_stream, tempfile.NamedTemporaryFile(
                dir=raw_dir, prefix=".dvf-extract-", delete=False,
            ) as out:
                temporary = Path(out.name)
                shutil.copyfileobj(input_stream, out, length=1024 * 1024)
            temporary.replace(target)
            return target
    finally:
        if zip_path:
            zip_path.unlink(missing_ok=True)
