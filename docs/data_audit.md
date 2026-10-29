# Reproducible source-to-export audit

Each new snapshot ingestion runs an independent audit after parsing. The audit
reads the original pipe-delimited TXT with Python's CSV reader, hashes its raw
bytes with SHA-256, and independently queries the resulting Parquet partitions
with DuckDB. It compares total rows and row counts by department, reports exact
duplicate canonical rows and the observed mutation-date range, and checks the
source hash against the registered version. A mismatch stops ingestion, so the
weekly publication job cannot publish that snapshot.

Run the same check manually after restoring a snapshot:

```bash
python -m src.main audit /path/to/valeursfoncieres-2024.txt \
  --year 2024 --version 1 \
  --registry source_files.csv \
  --parquet parquet \
  --manifest exports/manifest.json \
  --output audit-2024-v1.json
```

The command exits with status `0` only if the TXT and Parquet agree and every
available registered or published source hash matches. At least one of the
source registry or export manifest must be available. The JSON report contains
no local source paths. A third party can repeat the check from the public data host:
download the versioned `sources/<year>/version=<n>/...txt.gz` and matching
`details/<year>/version=<n>/` Parquet partitions from the linked manifest,
decompress the TXT without text conversion, download the manifest, then run the
comparison after placing the Parquet partitions under
`parquet/millesime=<year>/version=<n>/` and passing the manifest with
`--manifest /path/to/manifest.json`. The SHA-256 in the manifest is for the
decompressed source TXT bytes.

This validates byte provenance, row preservation, department partitioning,
and deterministic duplicate reporting. It does not prove that DGFiP's source
records are factually correct; that requires reconciliation with the official
publication and its documentation. The origin and reuse terms are documented
in the [DGFiP data.gouv.fr dataset](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres).
