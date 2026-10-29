# DVF Explorer roadmap

## Goal

DVF Explorer est un outil public pour retrouver et consulter facilement les
ventes immobilières publiées dans les données DVF. Il doit couvrir les années
disponibles, y compris les archives historiques sauvegardées localement,
permettre de rechercher, filtrer et trier les ventes, d’examiner le détail
d’une transaction et de télécharger les données publiques. Le projet conserve
les publications successives, automatise l’intégration des futures publications
et attribue clairement les données à la DGFiP en renvoyant vers data.gouv.fr.

## Delivery order

### Local pipeline

- **Data audit (implemented):** every new ingestion compares independent raw-TXT
  CSV counts and per-department counts with the generated Parquet, checks the
  source SHA-256 against the registry, reports exact duplicate rows and date
  range, and stops on mismatches. `python -m src.main audit` also checks the
  export manifest and emits a path-free JSON report.
- **013 — Public repository hygiene:** attribution, license, ignore rules, and
  crawler protections.
- **001 — Source registry:** record byte hashes and version metadata without
  storing private source paths.
- **002 — Typed parser:** normalize supported source headers into deterministic
  department-partitioned Parquet and expose a unified DuckDB view.
- **003 — Stable identities:** normalized row hashes and mutation keys.
- **004 — Snapshot comparison:** classify additions, modifications, removals,
  and duplicates while retaining prior values.

### Data delivery and geography

- **016 — Public code repository:** publish this code repository; never publish
  the private workspace repository.
- **000 — Hosting validation:** GitHub Releases failed CORS/no-index checks;
  the Site's same-origin R2 routes support byte ranges and no-index headers.
- **005 — Historical import:** local `import-archive` command stages TXT or ZIP
  snapshots, processes them in millésime/version order, and keeps source paths
  and credentials local.
- **006 — Geography (implemented for current publications):** discover matching
  geospatial resources, publish the original files and department indexes, and
  report match coverage by year. The weekly refresh handles revisions.
- **015 — Historical parcel matching:** exact parcel matching is implemented
  wherever an official compatible geolocation publication exists. Older rows
  without a defensible exact match remain unlocated; do not infer coordinates
  from an address or a neighboring parcel. Extend coverage when historical
  archives and compatible parcel vintages are available.
- **007 — Export contract:** versioned department Parquet, year-level KPI and
  search bundles, source archives, row-history files, and an attribution-rich
  manifest are published to the separate data host.
- **008 — Scheduled refresh:** a weekly Actions workflow discovers resources
  dynamically, compares changed snapshots against the previous public Parquet,
  publishes versioned files, and commits safe source metadata only.
- **014 — Backup and restore:** document and exercise a reproducible backup
  and restore path. The public data host retains immutable source and Parquet
  versions; `python -m src.main restore` restores a chosen snapshot locally.

### Explorer fronts and operations

- **011 — Claude artifact:** provide national KPIs, place search, details, and
  maps, with the required no-index protections.
- **012 — ChatGPT Site:** provide the same user features against the shared
  export contract, with the required no-index protections.
- **009 — Repository-size alert:** warn before code repository growth becomes
  operationally unsafe. `.github/workflows/repository_health.yml` warns at
  100 MiB and fails at 500 MiB.
- **010 — Scheduled-job monitoring:** surface refresh failures and stale runs.
  The daily health workflow fails if the latest weekly refresh failed or if
  the most recent successful refresh is more than nine days old.

### Sale explorer usability backlog

- **UI-001 — Result semantics and detail (implemented):** define a result as a source row and
  clearly explain when one mutation spans multiple properties or parcels.
- **UI-002 — National search (partially implemented):** search every published
  department without requiring a commune first; support department, postal
  code, commune, cadastral section, and year scopes. When geocoding returns a
  street/number, the transaction filter is prefilled and applied as a text
  match. Exact-address precision, formatting variants, and search usability
  still need validation against known records and users.
- **UI-003 — Filters (implemented):** add date bounds, price and surface ranges, rooms, local
  type, mutation nature, and removable active filters with input validation.
- **UI-004 — Results controls (implemented):** exact result count, sortable columns, stable
  ordering, selectable page size, and first/previous/next/last navigation.
- **UI-005 — Shareable state (partially implemented):** encode territory, year,
  filters, sort, page, and selected sale in the URL; restore the view on reload
  and browser navigation. Missing sale links now report that the linked row is
  unavailable instead of opening another row. Browser-history and shared-link
  journeys still need validation against live published data.
- **UI-006 — Detail and export (implemented):** show available source fields and export all
  normalized source fields and export all filtered results, with a clear notice
  when an export is large.
- **UI-007 — Map and geography (implemented):** synchronize list and map selection; publish
  only defensible geographic matches and show when rows have no coordinates.
- **UI-008 — Indicator explorer (partially implemented):** search, sort, paginate,
  and open commune sales from the commune indicators. Each row now displays its
  year, all-years counts distinguish commune-year results from distinct
  communes, the latest available year is selected after URL restoration, and a
  selected commune shows its published median-price-per-square-metre series,
  with source semester labels where available. The chart separately labels
  total mutation counts and explains that the eligible €/m² sample count is not
  present in the current KPI contract. Statistical definitions and the full
  location deep dive still need independent data review and design work.
- **UI-009 — Mobile and keyboard (implementation present, validation pending):**
  filter panels, result tables, suggestions, and sale details have responsive
  and keyboard affordances. Confirm the core user journeys with accessibility
  checks and representative users before marking complete.
- **UI-010 — Nearby comparable locations:** add an explicit radius selector and
  nearby commune/neighborhood results with distance, property mix, period,
  sample size, price level, and trend. Use defensible official geographic
  points or boundaries; do not use transaction-parcel centroids as commune
  locations. Define similarity criteria and show when the available sample is
  too small.
- **UI-011 — Address and cadastral precision:** verify that address queries
  match the published DVF number/street fields and that section queries match
  both INSEE code and cadastral section. Clearly label when summaries fall back
  to commune-level KPIs.
- **UI-012 — KPI observation counts:** publish per-metric eligible sample counts
  (especially mutations with a usable built surface for €/m²) alongside total
  mutations. Keep the observation unit and aggregation rules in the export
  contract, and regenerate all currently published annual KPI bundles.

The source data currently present on the separate data host covers 2021–2026.
Official geolocation files and department indexes cover 2021-S2 through
2026-S1; measured row coverage ranges from 95.0% to 98.8%. Matching uses the
mutation date, disposition, department, and parcel identifier. Rows without a
unique valid match remain in the results without coordinates. Both source CSVs
and indexes are downloadable from the Site and refreshed weekly.

Historical local publications from 2014 onward still need to be located and
imported before that part of the goal is complete. The sale table currently
queries published Parquet files in the browser; nationwide searches can involve
many department files, so a more efficient query service or search index may be
needed as coverage grows.

The independent raw-TXT-to-Parquet audit passes for every local published
snapshot currently available (2021–2026). It confirmed matching total and
department row counts and registered source checksums. Re-run it for each
historical archive as it is recovered; audit scope and limitations are in
[`docs/data_audit.md`](data_audit.md).

## Data handling gates

- Never commit raw DVF files or generated transaction-level exports to this
  repository; store downloadable snapshots and exports only on the separate
  Site data host.
- Do not expose private filesystem paths, archive credentials, or user account
  details in source, logs, or metadata.
- Do not enable person re-identification or external search indexing of DVF
  information.
- Attribute the source in the Site and every manifest, preserve its reuse terms,
  and keep all data responses out of search indexes.
