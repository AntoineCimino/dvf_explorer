"""Import archived DVF text files without storing their private source paths."""

from __future__ import annotations

import gzip
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from src.sources import millesime_from_name


_SOURCE_NAME = re.compile(r"valeursfoncieres[-_]20\d{2}(?:[-_]s[12])?\.txt$", re.I)


def _is_source(name: str) -> bool:
    return bool(_SOURCE_NAME.fullmatch(name))


def _order(name: str) -> tuple[int, int, str]:
    year = millesime_from_name(name)
    season = re.search(r"[-_]s([12])\.txt$", name, re.I)
    return year, int(season.group(1)) if season else 0, name.casefold()


def collect_sources(source: Path, staging_dir: Path) -> list[Path]:
    """Find and stage supported TXT, TXT.GZ, or ZIP publications by basename."""
    source, staging_dir = Path(source), Path(staging_dir)
    if not source.exists():
        raise FileNotFoundError("DVF archive path does not exist")
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged: dict[str, Path] = {}

    def save(name: str, stream) -> None:
        if not _is_source(name):
            return
        target = staging_dir / name
        with tempfile.NamedTemporaryFile(dir=staging_dir, prefix=".dvf-import-", delete=False) as out:
            temporary = Path(out.name)
            shutil.copyfileobj(stream, out, length=1024 * 1024)
        temporary.replace(target)
        staged[name.casefold()] = target

    paths = [source] if source.is_file() else sorted(source.rglob("*"))
    for path in paths:
        if not path.is_file():
            continue
        suffix = path.name.casefold()
        if suffix.endswith(".txt"):
            if _is_source(path.name):
                with path.open("rb") as stream:
                    save(path.name, stream)
        elif suffix.endswith(".txt.gz"):
            name = path.name[:-3]
            if _is_source(name):
                with gzip.open(path, "rb") as stream:
                    save(name, stream)
        elif suffix.endswith(".zip"):
            with zipfile.ZipFile(path) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    name = Path(member.filename.replace("\\", "/")).name
                    if _is_source(name):
                        with archive.open(member) as stream:
                            save(name, stream)

    if not staged:
        raise ValueError("No files named valeursfoncieres-YYYY[‑s1|‑s2].txt were found")
    return sorted(staged.values(), key=lambda item: _order(item.name))
