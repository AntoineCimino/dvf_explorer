from src.keys import mutation_key, row_hash


def test_row_hash_normalizes_whitespace_and_decimal_format():
    left = {"commune": " Paris  ", "valeur_fonciere": "100,00"}
    right = {"commune": "paris", "valeur_fonciere": "100.0"}
    assert row_hash(left) == row_hash(right)


def test_price_change_keeps_mutation_key():
    left = {
        "date_mutation": "2024-01-02", "insee_code": "75056", "no_disposition": "1",
        "code_departement": "75", "code_commune": "056", "prefixe_section": "000",
        "section": "AB", "no_plan": "123", "valeur_fonciere": "100000",
    }
    right = {**left, "valeur_fonciere": "125000"}
    assert mutation_key(left) == mutation_key(right)
    assert row_hash(left) != row_hash(right)
