"""Command-line entry point for the local DVF pipeline."""

import argparse
from pathlib import Path

from src.diff import compare_versions, read_snapshot_rows, write_history_events
from src.parse import create_view, parse_file
from src.sources import fingerprint, millesime_from_name, read_registry, register_source


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dvf-explorer")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="register and parse one source snapshot")
    ingest.add_argument("source", type=Path)
    ingest.add_argument("--origin", choices=("kdrive", "datagouv"), required=True)
    ingest.add_argument("--registry", type=Path, default=Path("source_files.csv"))
    ingest.add_argument("--parquet", type=Path, default=Path("parquet"))
    ingest.add_argument("--history", type=Path, default=Path("data/row_history"))

    parse = commands.add_parser("parse", help="parse one source file into Parquet")
    parse.add_argument("source", type=Path)
    parse.add_argument("--parquet", type=Path, default=Path("parquet"))

    view = commands.add_parser("view", help="show row count in the Parquet dataset")
    view.add_argument("--parquet", type=Path, default=Path("parquet"))

    args = parser.parse_args(argv)
    if args.command == "ingest":
        checksum, _ = fingerprint(args.source)
        registry = read_registry(args.registry)
        year = millesime_from_name(args.source.name)
        existing = next((row for row in registry if row["sha256"] == checksum), None)
        version = int(existing["version"]) if existing else max(
            (int(row["version"]) for row in registry if int(row["millesime"]) == year), default=0
        ) + 1
        snapshot_dir = args.parquet / f"millesime={year}" / f"version={version}"
        if existing and snapshot_dir.exists():
            print("Source bytes already registered and parsed; no work needed.")
            return 0
        outputs = parse_file(args.source, args.parquet, version=version)
        if version > 1:
            previous = read_snapshot_rows(args.parquet, millesime=year, version=version - 1)
            current = read_snapshot_rows(args.parquet, millesime=year, version=version)
            events, counts = compare_versions(
                previous, current, previous_version=version - 1, current_version=version,
            )
            write_history_events(
                events, args.history, millesime=year,
                previous_version=version - 1, current_version=version,
            )
            print(f"Comparison summary: {counts}")
        if existing is None:
            register_source(args.source, args.registry, origin=args.origin)
        print(f"Processed version {version} for {year}; wrote {len(outputs)} partitions.")
        return 0
    if args.command == "parse":
        outputs = parse_file(args.source, args.parquet)
        print(f"Wrote {len(outputs)} department partitions.")
        return 0
    connection = create_view(args.parquet)
    print(connection.execute("SELECT count(*) FROM dvf").fetchone()[0])
    connection.close()
    return 0

if __name__ == "__main__":
    main()
