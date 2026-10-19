# DVF Explorer roadmap

## Goal

Preserve successive DGFiP DVF snapshots, track transaction-row changes, and
provide geographic summaries and transaction details through two browser
explorers. Keep source data and generated datasets outside the public code
repository. The public Site serves downloadable data from a separate host with
explicit attribution and crawler restrictions.

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
  and restore path.

### Explorer fronts and operations

- **011 — Claude artifact:** provide national KPIs, place search, details, and
  maps, with the required no-index protections.
- **012 — ChatGPT Site:** provide the same user features against the shared
  export contract, with the required no-index protections.
- **009 — Repository-size alert:** warn before code repository growth becomes
  operationally unsafe.
- **010 — Scheduled-job monitoring:** surface refresh failures and stale runs.

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
