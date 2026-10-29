# Run-summary annotation (dev_monitor contract)

The last step of `.github/workflows/weekly_sync.yml` (`if: always()`) runs
`python -m src.run_summary <sync-log> <duration_seconds>`. It parses the stdout of `src.main sync`
(no extra state) and emits GitHub annotations that dev_monitor reads instead of a local ledger:

```
::notice title=run-summary::new_version=yes|no files_downloaded=N rows_added=N rows_changed=N rows_removed=N duration_seconds=N
::warning title=run-alert::<one-sentence reason>     (only when an anomaly is detected)
```

- `new_version`: at least one millésime was republished (`Published bundle prepared ...`).
- `files_downloaded`: publications discovered on data.gouv.fr (all are downloaded each run).
- `rows_added` / `rows_changed` / `rows_removed`: summed `added` / `modified` / `removed` of every
  `Comparison ...` line. History is never deleted; `rows_removed` > 0 means rows vanished from the source.
- `duration_seconds`: wall time from the start of the sync step to the summary step.

`run-alert` reasons (wording mirrors the `counter_labels` in `jobs.yaml`): "No files downloaded ..."
(sync failed or log missing), or "N rows removed from the official source ..." (`rows_removed` > 0).
Keys are stable; new keys may be appended. The step always exits 0.
