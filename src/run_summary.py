"""Build the dev_monitor run-summary annotation from the weekly sync's stdout log.

Usage: python -m src.run_summary <sync-log> <duration_seconds>
Contract: docs/run_summary.md. Never fails the workflow (always exits 0).
"""
import ast
import re
import sys
from pathlib import Path

_DISCOVERED = re.compile(r"^Discovered (\d+) DVF publications")
_COMPARISON = re.compile(r"^Comparison \d{4} v\d+→v\d+: (\{.*\})$")
_PUBLISHED = re.compile(r"^Published bundle prepared for \d{4} version \d+")


def build_summary(log_text: str | None, duration_seconds: int) -> tuple[str, str | None]:
    """Return (notice key=value line, warning reason or None)."""
    counters = {"files_downloaded": 0, "rows_added": 0, "rows_changed": 0, "rows_removed": 0}
    new_version = False
    for line in (log_text or "").splitlines():
        line = line.strip()
        if match := _DISCOVERED.match(line):
            # every discovered publication is downloaded in a non-dry-run sync
            counters["files_downloaded"] = int(match.group(1))
        elif match := _COMPARISON.match(line):
            counts = ast.literal_eval(match.group(1))
            counters["rows_added"] += int(counts.get("added", 0))
            counters["rows_changed"] += int(counts.get("modified", 0))
            counters["rows_removed"] += int(counts.get("removed", 0))
        elif _PUBLISHED.match(line):
            new_version = True
    notice = " ".join(
        [f"new_version={'yes' if new_version else 'no'}"]
        + [f"{key}={value}" for key, value in counters.items()]
        + [f"duration_seconds={max(0, int(duration_seconds))}"]
    )
    alert = None
    if not log_text or not counters["files_downloaded"]:
        alert = "sync produced no publication report (step failed or log missing)"
    elif counters["rows_removed"]:
        alert = f"{counters['rows_removed']} rows disappeared from the official source between versions"
    return notice, alert


def main(argv: list[str]) -> int:
    path, duration = Path(argv[0]), int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 0
    try:
        log_text = path.read_text(encoding="utf-8")
    except OSError:
        log_text = None
    notice, alert = build_summary(log_text, duration)
    print(f"::notice title=run-summary::{notice}")
    if alert:
        print(f"::warning title=run-alert::{alert}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
