"""Multiset comparison for successive publications of one DVF millésime."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from src.keys import mutation_key, row_hash


def compare_versions(
    previous_rows: Iterable[Mapping[str, Any]],
    current_rows: Iterable[Mapping[str, Any]],
    *,
    previous_version: int,
    current_version: int,
    window_expired: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Return row-level history events and counts for two complete snapshots.

    Duplicate rows are compared as a multiset. An old row paired with a new
    row for the same cadastral disposition becomes a modification; unmatched
    removals are retained and flagged according to whether the year left the
    source's publication window.
    """
    if current_version <= previous_version:
        raise ValueError("current_version must be greater than previous_version")
    old_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    new_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in previous_rows:
        snapshot = dict(row)
        old_groups[row_hash(snapshot)].append(snapshot)
    for row in current_rows:
        snapshot = dict(row)
        new_groups[row_hash(snapshot)].append(snapshot)

    events: list[dict[str, Any]] = []
    counts = Counter(added=0, removed=0, modified=0, unchanged=0)
    unmatched_old: list[dict[str, Any]] = []
    unmatched_new: list[dict[str, Any]] = []

    for digest in sorted(old_groups.keys() | new_groups.keys()):
        old = sorted(old_groups.get(digest, []), key=lambda r: str(r))
        new = sorted(new_groups.get(digest, []), key=lambda r: str(r))
        same = min(len(old), len(new))
        if same:
            events.append({
                "row_hash": digest,
                "mutation_key": mutation_key(new[0]),
                "first_seen_version": previous_version,
                "last_seen_version": current_version,
                "status": "unchanged",
                "flag": None,
                "count": same,
                "old_row": old[0],
                "new_row": new[0],
                "changes": {},
            })
            counts["unchanged"] += same
        unmatched_old.extend(old[same:])
        unmatched_new.extend(new[same:])

    old_by_mutation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    new_by_mutation: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in unmatched_old:
        old_by_mutation[mutation_key(row)].append(row)
    for row in unmatched_new:
        new_by_mutation[mutation_key(row)].append(row)

    remaining_old, remaining_new = [], []
    for key in sorted(old_by_mutation.keys() | new_by_mutation.keys()):
        old = sorted(old_by_mutation.get(key, []), key=lambda r: (row_hash(r), str(r)))
        new = sorted(new_by_mutation.get(key, []), key=lambda r: (row_hash(r), str(r)))
        paired = min(len(old), len(new))
        for old_row, new_row in zip(old[:paired], new[:paired]):
            changes = {
                field: {"old": old_row.get(field), "new": new_row.get(field)}
                for field in sorted(old_row.keys() | new_row.keys())
                if old_row.get(field) != new_row.get(field)
            }
            events.append({
                "row_hash": row_hash(new_row),
                "mutation_key": key,
                "first_seen_version": previous_version,
                "last_seen_version": current_version,
                "status": "modified",
                "flag": None,
                "count": 1,
                "old_row": old_row,
                "new_row": new_row,
                "changes": changes,
            })
            counts["modified"] += 1
        remaining_old.extend(old[paired:])
        remaining_new.extend(new[paired:])

    for row in remaining_old:
        events.append({
            "row_hash": row_hash(row),
            "mutation_key": mutation_key(row),
            "first_seen_version": previous_version,
            "last_seen_version": previous_version,
            "status": "removed",
            "flag": "hors_fenetre" if window_expired else "retiree",
            "count": 1,
            "old_row": row,
            "new_row": None,
            "changes": {},
        })
        counts["removed"] += 1
    for row in remaining_new:
        events.append({
            "row_hash": row_hash(row),
            "mutation_key": mutation_key(row),
            "first_seen_version": current_version,
            "last_seen_version": current_version,
            "status": "added",
            "flag": None,
            "count": 1,
            "old_row": None,
            "new_row": row,
            "changes": {},
        })
        counts["added"] += 1

    events.sort(key=lambda event: (event["mutation_key"], event["status"], event["row_hash"]))
    return events, dict(counts)
