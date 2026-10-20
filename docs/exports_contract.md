# Public data export contract

The ChatGPT Site and future fronts consume the same files from the Site's R2
data host. The code repository contains neither source TXT files nor generated
transaction data.

## Attribution and reuse

Every manifest and the Site identify the source as **DGFiP — Demandes de
valeurs foncières**, link to the [data.gouv.fr dataset](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres),
and state **Licence Ouverte 2.0**. Reuse must follow the dataset's conditions,
including the prohibition on indirect re-identification and external search
indexing. All Site data responses carry `X-Robots-Tag: noindex, nofollow,
noarchive`; `robots.txt` disallows crawling.

## Manifest

`exports/manifest.json` is the publication pointer. It is uploaded last so it
never points to files that are still being transferred. It contains:

- `contract_version`, `generated_at`, and the `source` attribution object;
- `kpis` and `search_index`, immutable JSON index files mapping years to
  compressed JSON bundles;
- `departments[code].details[year]`, pointing to the currently published
  department Parquet file for that year;
- `snapshots[year]`, describing the current source version, SHA-256, raw
  download and Parquet paths;
- `snapshot_history[year][]`, retaining each published version and its
  downloadable source and department Parquet files;
- `row_history[]`, listing Parquet files containing additions, modifications,
  or removals between successive source versions.
- `geography[year]`, with the official geolocated source archive, immutable
  version, department lookup files, and measured row match coverage; previous
  versions are retained in `geography_history[year]`.
- `geography_source`, attributing the companion dataset to Etalab and linking
  to its [data.gouv.fr page](https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres-geolocalisees).

## Files

- `sources/<year>/version=<n>/<source-name>.txt.gz`: deterministic gzip of the
  exact source TXT bytes; decompressing it reproduces the source file.
- `details/<year>/version=<n>/<department>.parquet`: typed transaction rows for
  that source version, partitioned by department. Previous versions remain
  available.
- `history/<year>/versions=<old>-<new>.parquet`: changed rows and old/new
  values; unchanged rows are represented by the retained source snapshots and
  an unchanged count in the refresh summary.
- `kpis/<year>.json.gz` and `search/<year>.json.gz`: year-level indicators and
  place search indexes. The browser fetch layer decompresses these gzip bundles.
- `geography/sources/<year>/version=<n>/<source-name>.csv.gz`: original public
  DVF geolocation publication, retained byte-for-byte.
- `geography/<year>/version=<n>/<department>.parquet`: unique parcel and
  transaction keys with validated coordinates, joined to sales by the browser.

## Hosting protocol

- Public reads: `GET` and `HEAD /api/data/<export-path>` on the Site origin.
  The Worker serves byte ranges for Parquet and marks every response no-index.
- Authenticated writes: `PUT /api/upload/<export-path>` with
  `Authorization: Bearer <DVF_UPLOAD_TOKEN>`. The token is stored in Sites and
  GitHub Actions secrets, never in source or logs.
- Refresh jobs write new versioned files first, then indicators and indexes,
  and the manifest last. They never delete prior source or detail versions.

## Refresh behavior

The weekly job discovers resources from the data.gouv.fr dataset API and
downloads each current transaction resource. It verifies the official resource
checksum when supplied, then computes SHA-256 over the extracted source TXT.
Byte-identical files are skipped. A changed file is parsed, compared with the
previous public snapshot, exported under a new version, and added to the
manifest. The safe `source_files.csv` registry is committed to GitHub; raw data,
Parquet, and row history are uploaded only to the separate data host.

The same weekly job discovers current DVF geolocation CSV.GZ resources from the
official companion dataset. It verifies the published checksum and size,
matches parcel identifiers against the current raw snapshot, reports coverage,
and uploads immutable source and department indexes. A publication is skipped
when its resource metadata and public manifest paths are unchanged; the job
does not need previous exports on its ephemeral runner disk.
