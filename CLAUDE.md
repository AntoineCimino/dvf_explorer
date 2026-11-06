# CLAUDE.md — dvf_explorer

Agent instructions for the dvf_explorer project. Monorepo root `CLAUDE.md` (when developed inside the parent monorepo) rules (critical rules, orchestration, backlog format) apply on top of this file.

## Commands

```bash
python -m src.main --help
pytest tests/ -v
```

## Backlog

`docs/roadmap.md`

## DPE ownership

The former data-web-framework DPE prototype now lives in `dpe/` as the isolated
`dpe_pilot` package. Read `dpe/AGENTS.md`, `dpe/README.md` and
`docs/dpe_backlog.md` for DPE work. The old generic framework is archived in the
parent workspace; do not develop DPE there. No DPE startup/import/schema change
is wired into the production DVF CLI, weekly workflow or public fronts.
