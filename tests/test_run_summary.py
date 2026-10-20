from src.run_summary import build_summary, main

LOG = """Discovered 5 DVF publications from data.gouv.fr.
Unchanged: valeursfoncieres-2021.txt
Comparison 2024 v2→v3: {'added': 10, 'modified': 4, 'removed': 0, 'unchanged': 99}
Published bundle prepared for 2024 version 3: 12 files; 14 history events.
Comparison 2025 v1→v2: {'added': 2, 'modified': 1, 'removed': 0, 'unchanged': 5}
"""


def test_new_version_counters():
    notice, alert = build_summary(LOG, 125)
    assert notice == ("new_version=yes files_downloaded=5 rows_added=12 rows_changed=5 "
                      "rows_removed=0 duration_seconds=125")
    assert alert is None


def test_unchanged_run():
    notice, alert = build_summary("Discovered 3 DVF publications from data.gouv.fr.\nNo source changed\n", 40)
    assert notice.startswith("new_version=no files_downloaded=3 rows_added=0")
    assert alert is None


def test_removed_rows_alert():
    _, alert = build_summary(LOG.replace("'removed': 0, 'unchanged': 5", "'removed': 7, 'unchanged': 5"), 1)
    assert alert and "7 rows" in alert


def test_missing_log_alerts(tmp_path, capsys):
    assert main([str(tmp_path / "absent.txt"), "9"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("::notice title=run-summary::new_version=no files_downloaded=0")
    assert out[0].endswith("duration_seconds=9")
    assert out[1].startswith("::warning title=run-alert::")
