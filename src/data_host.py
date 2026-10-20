"""Read published snapshot inputs and stream public export files to the Site."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import http.client
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


USER_AGENT = "dvf-explorer/0.1 (data host client)"


def fetch_manifest(site_url: str, exports_dir: Path) -> dict | None:
    url = site_url.rstrip("/") + "/api/data/manifest.json"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=30) as response:
            manifest = json.load(response)
    except Exception as error:
        if getattr(error, "code", None) == 404:
            return None
        raise RuntimeError("Could not read the current public data manifest") from None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("snapshots", {}), dict):
        raise ValueError("The existing data manifest has an unsupported schema")
    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)
    (exports_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for path in (manifest.get("kpis"), manifest.get("search_index")):
        if isinstance(path, str):
            _download_object(site_url, path, exports_dir / path)
    return manifest


def restore_snapshot_year(
    site_url: str,
    manifest: dict,
    parquet_root: Path,
    exports_root: Path,
    *,
    year: int,
    version: int,
) -> int:
    saved = None
    for candidate in manifest.get("snapshot_history", {}).get(str(year), []):
        if int(candidate.get("version", -1)) == version:
            saved = candidate
            break
    if saved is None:
        current = manifest.get("snapshots", {}).get(str(year), {})
        if int(current.get("version", -1)) == version:
            saved = current
    if saved is None:
        raise ValueError(f"Published snapshot for {year} has no version {version}")
    details = saved.get("details", {})
    if not details:
        raise ValueError(f"Published snapshot for {year} has no department files")
    restored = 0
    exports_root = Path(exports_root)
    raw_source = saved.get("raw_source")
    if raw_source:
        raw_source = _safe_relative(raw_source)
        raw_target = exports_root / raw_source
        _download_object(site_url, raw_source, raw_target)
        expected_sha256 = saved.get("source_sha256")
        if expected_sha256:
            digest = hashlib.sha256()
            try:
                with gzip.open(raw_target, "rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
            except (OSError, EOFError):
                raw_target.unlink(missing_ok=True)
                raise ValueError(f"Restored source archive for {year} version {version} is invalid") from None
            if digest.hexdigest() != expected_sha256:
                raw_target.unlink(missing_ok=True)
                raise ValueError(f"Restored source checksum for {year} version {version} does not match the manifest")
        restored += 1
    for department, relative in details.items():
        if not re.fullmatch(r"[0-9A-Za-z]{1,3}", str(department)):
            raise ValueError("Invalid department code in public manifest")
        _safe_relative(relative)
        target = Path(parquet_root) / f"millesime={year}" / f"version={version}" / f"dept={department}" / "part-00000.parquet"
        _download_object(site_url, relative, target)
        restored += 1
    history_prefix = f"history/{year}/"
    for relative in manifest.get("row_history", []) or []:
        if isinstance(relative, str) and relative.startswith(history_prefix):
            relative = _safe_relative(relative)
            _download_object(site_url, relative, exports_root / relative)
            restored += 1
    return restored


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {".", ".."} for part in path.parts):
        raise ValueError("Invalid export path in public manifest")
    return path.as_posix()


def _download_object(site_url: str, relative: str, target: Path) -> None:
    relative = _safe_relative(relative)
    url = site_url.rstrip("/") + "/api/data/" + "/".join(quote(part, safe="") for part in relative.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.download")
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=120) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Could not download published export {relative}") from None


def _content_type(path: Path) -> tuple[str, str | None]:
    if path.suffix == ".parquet":
        return "application/vnd.apache.parquet", None
    if path.name.endswith(".json.gz"):
        return "application/json", "gzip"
    if path.suffix == ".gz":
        return "application/gzip", None
    return "application/json; charset=utf-8", None


def _upload_one(site_url: str, relative: str, source: Path, token: str) -> None:
    parts = urlsplit(site_url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("Data host must be an HTTPS URL")
    relative = _safe_relative(relative)
    request_path = "/api/upload/" + "/".join(quote(part, safe="") for part in relative.split("/"))
    connection = http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=300)
    content_type, content_encoding = _content_type(source)
    try:
        connection.putrequest("PUT", request_path)
        connection.putheader("Authorization", f"Bearer {token}")
        connection.putheader("Content-Type", content_type)
        if content_encoding:
            connection.putheader("Content-Encoding", content_encoding)
        connection.putheader("Transfer-Encoding", "chunked")
        connection.endheaders()
        with source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                connection.send(f"{len(chunk):X}\r\n".encode("ascii"))
                connection.send(chunk)
                connection.send(b"\r\n")
        connection.send(b"0\r\n\r\n")
        response = connection.getresponse()
        response.read(4096)
        if response.status not in {200, 201, 204}:
            raise RuntimeError(f"Upload failed with HTTP {response.status} for {relative}")
    finally:
        connection.close()


def upload_exports(
    exports_dir: Path,
    site_url: str,
    token: str,
    *,
    paths: list[str] | None = None,
) -> int:
    """Stream changed local files; publish manifest last as the commit marker."""
    if not token:
        raise ValueError("DVF_UPLOAD_TOKEN is required to publish data exports")
    root = Path(exports_dir)
    if paths is None:
        files = sorted(path for path in root.rglob("*") if path.is_file() and not path.name.endswith(".tmp"))
    else:
        files = []
        for relative in paths:
            safe_path = _safe_relative(relative)
            candidate = root.joinpath(*PurePosixPath(safe_path).parts)
            if not candidate.is_file():
                raise FileNotFoundError(f"Missing export file: {safe_path}")
            files.append(candidate)
    files.sort(key=lambda path: (path.name == "manifest.json", path.as_posix()))
    data_files = [path for path in files if path.name != "manifest.json"]
    manifest_files = [path for path in files if path.name == "manifest.json"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(
            lambda path: _upload_one(site_url, path.relative_to(root).as_posix(), path, token),
            data_files,
        ))
    for path in manifest_files:
        _upload_one(site_url, path.relative_to(root).as_posix(), path, token)
    return len(files)
