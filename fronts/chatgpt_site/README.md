# DVF Explorer — ChatGPT Site

The Site front reads its versioned export manifest and performs transaction
queries locally in DuckDB-WASM. It includes national and commune indicators,
place search, filters, paginated transaction detail, CSV download, and a
clustered map.

## Data routes

- `GET /api/data/manifest.json` reads the published export manifest from the
  `BUCKET` R2 binding.
- `GET` and `HEAD /api/data/<path>` expose read-only files under `exports/` and
  preserve HTTP byte-range requests.
- `PUT /api/upload/<path>` accepts refresh files under `exports/` when the
  caller provides the `DVF_UPLOAD_TOKEN` secret.

The Site returns `X-Robots-Tag: noindex, nofollow, noarchive`, and
`public/robots.txt` disallows crawlers. The Site and every public data bundle
must identify the source as **DGFiP — Demandes de valeurs foncières** and link
to <https://www.data.gouv.fr/datasets/demandes-de-valeurs-foncieres>. Public
downloads are served from the separate R2 data host, never from GitHub. Upload
only published DVF snapshots and derived exports that comply with the source
reuse conditions; do not include private archive material or secrets.

## Development

Use the Sites plugin workflow for dependency installation, local preview,
packaging, source synchronization, and deployment. The checked-in
`.openai/hosting.json` stores the Site ID and the `BUCKET` binding name. Runtime
secrets stay in Sites, never in this source tree.
