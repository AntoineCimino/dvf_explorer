"""Track byte-exact versions of downloaded or archived DVF text files."""

import csv
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import tempfile


FIELDS = (
    "name",
    "millesime",
    "version",
    "sha256",
    "size",
    "fetched_at",
    "origin",
    "url",
    "last_modified",
)
FILENAME = re.compile(r"valeursfoncieres[-_](\d{4})(?:[-_]s\d+)?\.txt", re.IGNORECASE)
ORIGINS = {"kdrive", "datagouv"}


def millesime_from_name(name: str) -> int:
    """Extract the publication year from a DVF source filename."""
    match = FILENAME.fullmatch(name)
    if not match:
        raise ValueError(f"Unrecognized DVF filename: {name!r}")
    return int(match.group(1))


def fingerprint(path: Path) -> tuple[str, int]:
    """Hash original bytes without loading a full source file into memory."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def read_registry(path: Path) -> list[dict[str, str]]:
    """Read the public CSV registry, or return an empty registry if absent."""
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError(f"Unexpected source registry schema: {path}")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"Malformed source registry row: {path}")
    return rows


def register_source(
    source_path: Path,
    registry_path: Path,
    *,
    origin: str,
    url: str = "",
    last_modified: str = "",
    fetched_at: datetime | None = None,
) -> dict[str, str] | None:
    """Append a new content version; return None when its bytes are known.

    Only a source basename is persisted. A private kDrive URL is never stored.
    """
    source_path = Path(source_path)
    registry_path = Path(registry_path)
    year = millesime_from_name(source_path.name)
    if origin not in ORIGINS:
        raise ValueError(f"Unknown source origin: {origin!r}")
    if origin == "kdrive" and url:
        raise ValueError("Private archive URLs must not be recorded")

    checksum, size = fingerprint(source_path)
    rows = read_registry(registry_path)
    if any(row["sha256"] == checksum for row in rows):
        return None

    versions = [int(row["version"]) for row in rows if int(row["millesime"]) == year]
    timestamp = fetched_at or datetime.now(timezone.utc)
    if timestamp.utcoffset() is None:
        raise ValueError("fetched_at must include a timezone")
    row = {
        "name": source_path.name,
        "millesime": str(year),
        "version": str(max(versions, default=0) + 1),
        "sha256": checksum,
        "size": str(size),
        "fetched_at": timestamp.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "origin": origin,
        "url": url,
        "last_modified": last_modified,
    }
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", dir=registry_path.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            writer = csv.DictWriter(temporary, fieldnames=FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows([*rows, row])
        os.replace(temporary_path, registry_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return row
