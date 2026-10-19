"""Command-line entry point for importing, reconciling, and publishing DVF data."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from src.data_host import fetch_manifest, restore_snapshot_year, upload_exports
from src.datagouv import DATASET_API, discover_publications, download_publication
from src.diff import compare_snapshot_files
from src.exports import generate_year_exports, publish_raw_source
from src.import_archive import collect_sources
from src.parse import create_view, parse_file
from src.sources import fingerprint, millesime_from_name, read_registry, register_source


def ingest_file(
    source: Path,
    *,
    origin: str,
    registry_path: Path,
    parquet_root: Path,
    history_root: Path,
    url: str = "",
    last_modified: str = "",
) -> tuple[bool, int, int]:
    checksum, _ = fingerprint(source)
    registry = read_registry(registry_path)
    year = millesime_from_name(source.name)
    existing = next((row for row in registry if row["sha256"] == checksum), None)
    version = int(existing["version"]) if existing else max(
        (int(row["version"]) for row in registry if int(row["millesime"]) == year), default=0
    ) + 1
    snapshot_dir = parquet_root / f"millesime={year}" / f"version={version}"
    if existing and snapshot_dir.exists():
        return False, version, 0
    if version > 1:
        previous_dir = parquet_root / f"millesime={year}" / f"version={version - 1}"
        if not previous_dir.exists():
            raise FileNotFoundError(
                f"Previous snapshot {year} version {version - 1} is unavailable; restore it before comparing"
            )

    outputs = parse_file(source, parquet_root, version=version)
    event_count = 0
    if version > 1:
        history_file = history_root / f"millesime={year}" / f"versions={version - 1}-{version}" / "row_history.parquet"
        counts = compare_snapshot_files(
            parquet_root / f"millesime={year}" / f"version={version - 1}",
            parquet_root / f"millesime={year}" / f"version={version}",
            history_file,
            previous_version=version - 1,
            current_version=version,
        )
        event_count = counts["added"] + counts["removed"] + counts["modified"]
        print(f"Comparison {year} v{version - 1}→v{version}: {counts}")
    if existing is None:
        register_source(
            source, registry_path, origin=origin, url=url, last_modified=last_modified,
        )
    print(f"Processed {year} version {version}; wrote {len(outputs)} department partitions.")
    return True, version, event_count


def _command_ingest(args) -> int:
    changed, _, _ = ingest_file(
        args.source, origin=args.origin, registry_path=args.registry,
        parquet_root=args.parquet, history_root=args.history,
        url=args.url, last_modified=args.last_modified,
    )
    if not changed:
        print("Source bytes already registered and parsed; no work needed.")
    return 0


def _command_import_archive(args) -> int:
    if args.site_url and args.no_exports:
        raise ValueError("--site-url requires data exports")
    args.raw_dir.mkdir(parents=True, exist_ok=True)
    if args.site_url:
        fetch_manifest(args.site_url, args.exports)
    changed_count = 0
    with tempfile.TemporaryDirectory(prefix="dvf-archive-") as staging_name:
        sources = collect_sources(args.source, Path(staging_name))
        for staged in sources:
            raw_target = args.raw_dir / staged.name
            if not raw_target.exists() or fingerprint(raw_target)[0] != fingerprint(staged)[0]:
                temporary = raw_target.with_name(f".{raw_target.name}.tmp")
                shutil.copyfile(staged, temporary)
                temporary.replace(raw_target)
            changed, version, _ = ingest_file(
                raw_target, origin="kdrive", registry_path=args.registry,
                parquet_root=args.parquet, history_root=args.history,
            )
            year = millesime_from_name(raw_target.name)
            if changed:
                changed_count += 1
                checksum, _ = fingerprint(raw_target)
                current = next(row for row in read_registry(args.registry) if row["sha256"] == checksum)
                if not args.no_exports:
                    result = generate_year_exports(
                        args.parquet, args.exports, year=year, version=version,
                        source_name=current["name"], source_sha256=checksum,
                    )
                    raw_path = publish_raw_source(raw_target, args.exports, year=year, version=version)
                    result["files"].append(raw_path)
                    if version > 1:
                        _add_history_export(args.history, args.exports, year, version - 1, version)
                    print(f"Exported {year} version {version}: {len(result['files'])} files.")
    if changed_count and args.site_url:
        upload_exports(args.exports, args.site_url, os.environ.get("DVF_UPLOAD_TOKEN", ""))
        print("Uploaded historical snapshots and exports to the public data host.")
    if not changed_count:
        print("Archive already imported; no work needed.")
    return 0


def _add_history_export(history_root: Path, exports_root: Path, year: int, old_version: int, new_version: int) -> str | None:
    history_file = Path(history_root) / f"millesime={year}" / f"versions={old_version}-{new_version}" / "row_history.parquet"
    if not history_file.exists():
        return None
    target = Path(exports_root) / "history" / str(year) / f"versions={old_version}-{new_version}.parquet"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(history_file, target)
    relative = target.relative_to(exports_root).as_posix()
    manifest_path = Path(exports_root) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    history_paths = manifest.setdefault("row_history", [])
    if relative not in history_paths:
        history_paths.append(relative)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return relative


def _command_sync(args) -> int:
    publications = discover_publications(args.dataset_api)
    if not publications:
        raise RuntimeError("The official dataset API returned no DVF transaction resources")
    print(f"Discovered {len(publications)} DVF publications from data.gouv.fr.")
    if args.dry_run:
        for publication in publications:
            print(f"{publication.name} · {publication.filesize or 'unknown size'} bytes · updated {publication.last_modified or 'unknown'}")
        return 0

    remote_manifest = None
    if args.site_url:
        remote_manifest = fetch_manifest(args.site_url, args.exports)
        if remote_manifest:
            print(f"Loaded public data manifest with {len(remote_manifest.get('years', []))} millésimes.")

    changed_years: dict[int, tuple[int, str, str]] = {}
    for publication in publications:
        source = download_publication(publication, args.raw_dir / "datagouv")
        checksum, _ = fingerprint(source)
        registry = read_registry(args.registry)
        known = next((row for row in registry if row["sha256"] == checksum), None)
        if known:
            print(f"Unchanged: {publication.name}")
            if os.environ.get("DVF_EPHEMERAL_RAW") == "1":
                source.unlink(missing_ok=True)
            continue
        year = publication.millesime
        version = int(known["version"]) if known else max(
            (int(row["version"]) for row in registry if int(row["millesime"]) == year), default=0
        ) + 1
        if version > 1:
            previous_dir = args.parquet / f"millesime={year}" / f"version={version - 1}"
            if not previous_dir.exists():
                if not args.site_url or not remote_manifest:
                    raise FileNotFoundError(f"Previous snapshot for {year} is absent; a public data host is needed to restore it")
                restored = restore_snapshot_year(
                    args.site_url, remote_manifest, args.parquet, year=year, version=version - 1,
                )
                print(f"Restored {restored} previous {year} department partitions for comparison.")
        changed, version, events = ingest_file(
            source, origin="datagouv", registry_path=args.registry,
            parquet_root=args.parquet, history_root=args.history,
            url=publication.registry_url, last_modified=publication.last_modified,
        )
        if not changed:
            print(f"Already processed: {publication.name}")
            continue
        registry = read_registry(args.registry)
        metadata = next(row for row in registry if row["sha256"] == checksum)
        result = generate_year_exports(
            args.parquet, args.exports, year=year, version=version,
            source_name=metadata["name"], source_sha256=checksum,
        )
        raw_path = publish_raw_source(source, args.exports, year=year, version=version)
        result["files"].append(raw_path)
        if os.environ.get("DVF_EPHEMERAL_RAW") == "1":
            source.unlink(missing_ok=True)
        changed_years[year] = (version, checksum, metadata["name"])
        if version > 1:
            history_file = args.history / f"millesime={year}" / f"versions={version - 1}-{version}" / "row_history.parquet"
            if history_file.exists():
                target = args.exports / "history" / str(year) / f"versions={version - 1}-{version}.parquet"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(history_file, target)
                result["files"].append(target.relative_to(args.exports).as_posix())
                manifest_path = args.exports / "manifest.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                history_paths = manifest.setdefault("row_history", [])
                relative = target.relative_to(args.exports).as_posix()
                if relative not in history_paths:
                    history_paths.append(relative)
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Published bundle prepared for {year} version {version}: {len(result['files'])} files; {events} history events.")

    if changed_years and args.site_url:
        token = os.environ.get("DVF_UPLOAD_TOKEN", "")
        count = upload_exports(args.exports, args.site_url, token)
        print(f"Uploaded {count} export files; manifest is published last.")
    elif changed_years:
        print("Exports are local only. Set DVF_SITE_URL and DVF_UPLOAD_TOKEN to publish them.")
    else:
        print("No source changed; no exports were uploaded.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dvf-explorer")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="register and parse one source snapshot")
    ingest.add_argument("source", type=Path)
    ingest.add_argument("--origin", choices=("kdrive", "datagouv"), required=True)
    ingest.add_argument("--registry", type=Path, default=Path("source_files.csv"))
    ingest.add_argument("--parquet", type=Path, default=Path("parquet"))
    ingest.add_argument("--history", type=Path, default=Path("data/row_history"))
    ingest.add_argument("--url", default="")
    ingest.add_argument("--last-modified", default="")
    ingest.set_defaults(func=_command_ingest)

    archive = commands.add_parser("import-archive", help="import historical local TXT files or ZIP archives")
    archive.add_argument("source", type=Path, help="local archive file or directory")
    archive.add_argument("--registry", type=Path, default=Path("source_files.csv"))
    archive.add_argument("--raw-dir", type=Path, default=Path("data/raw_txt"))
    archive.add_argument("--parquet", type=Path, default=Path("parquet"))
    archive.add_argument("--history", type=Path, default=Path("data/row_history"))
    archive.add_argument("--exports", type=Path, default=Path("exports"))
    archive.add_argument("--no-exports", action="store_true", help="skip public bundles but retain local Parquet")
    archive.add_argument("--site-url", default=os.environ.get("DVF_SITE_URL", ""))
    archive.set_defaults(func=_command_import_archive)

    sync = commands.add_parser("sync", help="discover every current DVF publication and refresh changed millésimes")
    sync.add_argument("--dataset-api", default=DATASET_API)
    sync.add_argument("--site-url", default=os.environ.get("DVF_SITE_URL", ""))
    sync.add_argument("--registry", type=Path, default=Path("source_files.csv"))
    sync.add_argument("--raw-dir", type=Path, default=Path("data/raw_txt"))
    sync.add_argument("--parquet", type=Path, default=Path("parquet"))
    sync.add_argument("--history", type=Path, default=Path("data/row_history"))
    sync.add_argument("--exports", type=Path, default=Path("exports"))
    sync.add_argument("--dry-run", action="store_true")
    sync.set_defaults(func=_command_sync)

    parse = commands.add_parser("parse", help="parse one source file into Parquet")
    parse.add_argument("source", type=Path)
    parse.add_argument("--parquet", type=Path, default=Path("parquet"))
    parse.set_defaults(func=lambda args: print(f"Wrote {len(parse_file(args.source, args.parquet))} department partitions.") or 0)

    view = commands.add_parser("view", help="show row count in the Parquet dataset")
    view.add_argument("--parquet", type=Path, default=Path("parquet"))
    view.set_defaults(func=lambda args: _show_view(args.parquet))

    args = parser.parse_args(argv)
    return args.func(args)


def _show_view(parquet_root: Path) -> int:
    connection = create_view(parquet_root)
    print(connection.execute("SELECT count(*) FROM dvf").fetchone()[0])
    connection.close()
    return 0


if __name__ == "__main__":
    main()
