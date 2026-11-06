# DPE prototype — now maintained in DVF Explorer

Status: local experimental component, migrated from the private
`AntoineCimino/data-web-framework` repository on 2026-11-05. The source
repository is retained as an archive for possible future framework work.

This directory owns the transferred DPE code, tests, Docker setup and legacy
documentation. It is independent of the existing DVF pipeline: no DPE import,
PostGIS startup or schema change is added to DVF's CLI, weekly job or website.
Its package is named `dpe_pilot` to avoid colliding with DVF's `src` package.

## Actual capabilities and limits

- FastAPI search/statistics prototype, SQLAlchemy models and PostGIS schema.
- `ingest_from_data_gouv` is a stub which generates 1,000 **synthetic** buildings.
  It does not fetch official DPE data. Never publish these rows as observations.
- No implemented national import, DVF/DPE matching, frontend or production CI/CD.
- The demo rating thresholds, consumption units and recommendation values are
  not validated official DPE rules. Search distance semantics (geometry in
  EPSG:4326 versus metre radius), HTTP errors, response types and migrations
  also require review before reuse.
- The API startup creates an extension/tables. Do not point it at an existing
  DVF or production database. No application or database was started to migrate it.
- Dependencies stay in this directory; DVF's normal installation does not
  acquire the legacy API/geospatial stack.

## Local commands (not executed by the migration)

Use a dedicated environment and run from this directory. Copy `.env.example`
locally and replace its placeholder password; keep it out of Git. Configure a
matching `DATABASE_URL` for Python processes. Compose uses loopback port 55432.

```sh
python -m pip install -r requirements.txt
docker compose up -d postgres
python -m dpe_pilot.ingestion.dpe_ingest  # synthetic demo only; writes to DB
uvicorn dpe_pilot.main:app --host 127.0.0.1 --port 8000
python -m pytest -p no:cacheprovider tests/ -v
```

The Dockerfile builds the API image. Compose provisions only the optional demo
database; it does not deploy the public DVF site. Database-dependent tests remain
skipped and the health unit test does not exercise startup/migrations.

## Ownership, preservation and next work

- Active domain backlog: `../docs/dpe_backlog.md`; roadmap: `../docs/roadmap.md`.
- `MIGRATION.json` records source commit, every copied tracked file and hashes,
  adaptations and exclusions. Original history remains in the private archive.
- Local `.env`, datasets, Docker volumes and credentials were **not** copied into
  this public repository. No national DPE dataset exists among the tracked files.
  Any existing database volume must be inventoried/backed up separately before reuse.
- Original README/SETUP are under `docs/legacy/` with warnings; their performance
  and production claims are historical, not validation evidence.
- National DVF/DPE analysis requires the source/matching/quality backlog work,
  including unmatched/ambiguous records and temporal rules.

Future generic framework work may resume from `archived/biz/data-web-framework`
in the parent workspace, but DPE development belongs here; avoid two active copies.
