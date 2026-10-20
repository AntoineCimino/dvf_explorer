# Backup and restore

## Backups

The Site's separate data host is the durable backup for public DVF snapshots.
Each manifest points to immutable, versioned source archives and department
Parquet files. Later publications add versions; they do not overwrite earlier
ones. The GitHub repository stores only `source_files.csv` metadata and code,
not raw DVF or transaction exports.

## Restore a published year and version

The restore command downloads a selected snapshot's compressed source archive
and department Parquet files into the local export and Parquet directories.
It also downloads published row-history files for that year. The operation is
repeatable and does not write to the public data host.

```sh
python -m src.main restore \
  --site-url https://dvf-explorer.sci-cimino-eggrickx.chatgpt.site \
  --year 2025 \
  --version 1 \
  --exports exports \
  --parquet parquet
```

`--version` selects an exact retained publication version. If it is not present
in the public manifest, the command stops instead of silently selecting a
different version. Use the same command with another year and version to
restore additional snapshots. Keep generated Parquet and exported DVF files out
of Git; the repository ignore rules cover the default output directories.

To rebuild a local dataset from restored compressed source archives, pass the
corresponding `exports/sources/<year>/version=<n>` directory to
`import-archive`, with the intended registry, Parquet, history, and export
directories. Review the source hashes in `source_files.csv` and the generated
manifest before publishing any rebuilt bundle.

## Restore validation

After each restore, check the command's restored object count and confirm that
the selected year's `millesime=<year>/version=<version>` directory contains
department Parquet files. For a full recovery, restore every retained version
listed under that year in `exports/manifest.json` before resuming the scheduled
sync. A newly generated version needs its immediately preceding Parquet
version locally so the pipeline can compare changes.

The restore path was exercised against the public 2026 version 1 snapshot:
all 97 department Parquet files matched the local published copies by SHA-256,
and the restored gzip source archive decompressed successfully.
