# DPE domain backlog — 2026-11-05

## Context

The DPE prototype is now owned by DVF Explorer under `dpe/`; the generic
data-web-framework repository is archived. Owner intent: an open-source
public-interest view combining official DVF, recovered historical sales and
available national DPE records. Migration preserves a prototype, not a finished
national importer or validated diagnoses. No deployment/data publication is requested.

## TODO

### DPE-001 Stabilize and validate the inherited prototype
**Priority:** HIGH  **Size:** M  **Deps:** none
**Files:** `dpe/dpe_pilot/`, `dpe/tests/`, `dpe/README.md`, `dpe/requirements.txt`
**Origin:** DATA-WEB-FRAMEWORK-001 and the DPE portions of -002/-005.
**Work:** Review schema units and official rating definitions, EPSG:4326/metre
distance handling, UUID response serialization, exception handling, explicit
migrations and dependency compatibility. Add actual PostGIS integration tests;
keep the synthetic demo separate from real observations. Inventory old external
database volumes before attempting reuse.
**Done when:** documented commands work on an isolated test DB, spatial/response
contracts are tested, and no production DVF startup/job depends on the prototype.

### DPE-002 Implement official DPE source ingestion and versioning
**Priority:** HIGH  **Size:** L  **Deps:** DPE-001
**Files:** `dpe/dpe_pilot/ingestion/`, future source contract documentation
**Work:** Inventory official sources and coverage, dates/schema changes, identifiers,
reuse conditions, volume, incremental refresh, provenance, checksums and restore.
Replace the misleading `ingest_from_data_gouv` synthetic fallback with explicit
real/demo modes. Source failure must never silently manufacture observations.
**Done when:** bounded source-backed import and repeatability/audit tests pass;
national processing requires its own measured storage/runtime plan.

### DPE-003 Assess and validate DVF/DPE linkage (DVF-DPE-001)
**Priority:** MEDIUM  **Size:** L  **Deps:** DPE-002
**Files:** `docs/roadmap.md`, future matching and export modules
**Work:** Define energy performance versus data/diagnostic quality; match using
defensible building/address/parcel identifiers and time, retaining multiple DPE,
multi-property sales, uncertainty and unmatched records. Report sample sizes,
coverage and bias; do not treat a join as proof of physical diagnostic accuracy.
**Done when:** independently checked sample and matching protocol, explicit
limitations, attribution and existing non-re-identification/no-index gates.

### DPE-004 Design the combined explorer and deployment contract
**Priority:** MEDIUM  **Size:** L  **Deps:** DPE-003
**Files:** `fronts/`, `docs/exports_contract.md`, `dpe/`
**Origin:** DPE portions of DATA-WEB-FRAMEWORK-004/-005; owner's 2026-06-29 request
for filters, map, responsive UX and backend → full pilot → polish.
**Work:** Reuse DVF fronts where justified; define filters, maps, statistics,
latency, API/static export boundary, backup/restore and CI/CD. Generic SEO and
generator work stay frozen in the archived framework; combined DVF outputs
preserve no-index rather than copying its SEO traffic goal.
**Done when:** agreed design and measured resource/backup plan before deployment.
