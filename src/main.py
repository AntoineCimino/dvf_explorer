"""Command-line entry point for the local DVF pipeline."""

import argparse
from pathlib import Path

from src.parse import create_view, parse_file
from src.sources import fingerprint, read_registry, register_source


def main(argv=None):
    parser = argparse.ArgumentParser(prog="dvf-explorer")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="register and parse one source snapshot")
    ingest.add_argument("source", type=Path)
    ingest.add_argument("--origin", choices=("kdrive", "datagouv"), required=True)
    ingest.add_argument("--registry", type=Path, default=Path("source_files.csv"))
    ingest.add_argument("--parquet", type=Path, default=Path("parquet"))

    parse = commands.add_parser("parse", help="parse one source file into Parquet")
    parse.add_argument("source", type=Path)
    parse.add_argument("--parquet", type=Path, default=Path("parquet"))

    view = commands.add_parser("view", help="show row count in the Parquet dataset")
    view.add_argument("--parquet", type=Path, default=Path("parquet"))

    args = parser.parse_args(argv)
    if args.command == "ingest":
        checksum, _ = fingerprint(args.source)
        if any(row["sha256"] == checksum for row in read_registry(args.registry)):
            print("Source bytes already registered; no work needed.")
            return 0
        outputs = parse_file(args.source, args.parquet)
        row = register_source(args.source, args.registry, origin=args.origin)
        if row is None:
            print("Source bytes were registered concurrently; parsed output is available.")
            return 0
        print(f"Registered version {row['version']} for {row['millesime']}; wrote {len(outputs)} partitions.")
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
