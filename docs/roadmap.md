# DVF Explorer roadmap

## Goal

Preserve successive DGFiP DVF snapshots, track transaction-row changes, and
provide geographic summaries and transaction details through two browser
explorers. Keep source data and generated datasets outside the public code
repository unless a separate publication review confirms the hosting path and
data-use requirements.

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
- **000 — Hosting validation:** verify browser-compatible data access, CORS,
  range requests, and the selected host's crawler controls before releasing any
  transaction dataset.
- **005 — Historical import:** provide a local, resumable import interface;
  source paths and credentials must stay local.
- **006 — Geography:** discover matching geospatial resources and report match
  coverage by year.
- **015 — Historical parcel matching:** document historical cadastre coverage
  and fallbacks for older snapshots.
- **007 — Export contract:** define versioned national, department, commune,
  section, and detail exports for browser clients.
- **008 — Scheduled refresh:** discover current data resources dynamically,
  compare every changed publication, and publish only through an approved
  non-indexable data host.
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
  repository.
- Do not expose private filesystem paths, archive credentials, or user account
  details in source, logs, or metadata.
- Do not enable person re-identification or external search indexing of DVF
  information.
- Treat publication of historical or derived data as a separate release
  decision from publication of code.
