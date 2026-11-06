# DPE component instructions

Read this component's README and `../docs/dpe_backlog.md` before working here.
The `dpe_pilot` package is isolated from DVF's `src`; run component tests from
this directory, and run DVF's normal tests separately after changes.

Do not run ingestion, start the API/database or execute schema creation without
task authorization. Ingestion is synthetic, not official DPE data. Never import
private environment files, browser profiles or personal data from the archived
private repository into public DVF. Keep DPE dependencies isolated.
Production DVF jobs and datasets must not be modified by DPE prototype startup.
