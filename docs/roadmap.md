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
- **006 — Geography:** discover matching geospatial resources and report match
  coverage by year.
- **015 — Historical parcel matching:** document historical cadastre coverage
  and fallbacks for older snapshots.
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

- **UI-001 — Result semantics and detail:** define a result as a source row and
  clearly explain when one mutation spans multiple properties or parcels.
- **UI-002 — National search:** search every published department without
  requiring a commune first; default to the latest available year and support
  department, postal code, commune, and year scopes.
- **UI-003 — Filters:** add date bounds, price and surface ranges, rooms, local
  type, mutation nature, and removable active filters with input validation.
- **UI-004 — Results controls:** exact result count, sortable columns, stable
  ordering, selectable page size, and first/previous/next/last navigation.
- **UI-005 — Shareable state:** encode territory, year, filters, sort, page, and
  selected sale in the URL; restore the view on reload and browser navigation.
- **UI-006 — Detail and export:** show available source fields and export all
  filtered results, with a clear notice when an export is large.
- **UI-007 — Map and geography:** synchronize list and map selection; publish
  only defensible geographic matches and show when rows have no coordinates.
- **UI-008 — Indicator explorer:** search, sort, paginate, and open commune
  sales from the commune indicators.
- **UI-009 — Mobile and keyboard:** ensure filter panels, result tables,
  suggestions, and sale details remain usable on narrow screens and by keyboard.

The source data currently present on the separate data host covers 2021–2026.
Historical local publications from 2014 onward still need to be located and
imported before that part of the goal is complete. The sale table currently
queries published Parquet files in the browser; nationwide searches can involve
many department files, so a more efficient query service or search index may be
needed as coverage grows.

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
