from src.diff import compare_versions


def row(price, plan, city="75056"):
    return {
        "date_mutation": "2024-01-02", "nature_mutation": "Vente",
        "valeur_fonciere": str(price), "insee_code": city, "no_disposition": "1",
        "code_departement": city[:2], "code_commune": city[2:],
        "prefixe_section": "000", "section": "AB", "no_plan": str(plan),
    }


def test_multiset_add_remove_modify_and_duplicates():
    old = [row(100, 1), row(100, 1), row(200, 2), row(300, 3)]
    new = [row(100, 1), row(150, 2), row(400, 4)]
    events, counts = compare_versions(old, new, previous_version=1, current_version=2)
    assert counts == {"added": 1, "removed": 2, "modified": 1, "unchanged": 1}
    assert sum(event["count"] for event in events if event["status"] == "unchanged") == 1
    changed = next(event for event in events if event["status"] == "modified")
    assert changed["changes"]["valeur_fonciere"] == {"old": "200", "new": "150"}


def test_window_expiration_is_not_a_retirement():
    events, counts = compare_versions(
        [row(100, 1)], [], previous_version=1, current_version=2, window_expired=True,
    )
    assert counts["removed"] == 1
    assert events[0]["flag"] == "hors_fenetre"
