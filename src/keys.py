"""Stable row identity functions used by the version comparison pipeline."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping


HASH_SCHEMA_VERSION = 1


def _text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\s+", " ", text).casefold()
    # Decimal spellings such as 12,00 and 12.0 denote the same value.
    if re.fullmatch(r"-?\d+(?:[,.]\d+)?", text):
        try:
            return format(Decimal(text.replace(",", ".")).normalize(), "f")
        except InvalidOperation:
            pass
    return text


def row_hash(row: Mapping[str, Any]) -> str:
    """Hash every canonical field, excluding derived/version metadata."""
    payload = {
        "hash_schema_version": HASH_SCHEMA_VERSION,
        "row": {str(key): None if value is None else _text(value)
                for key, value in sorted(row.items())
                if key not in {"row_hash", "hash_schema_version", "status", "flag"}},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def mutation_key(row: Mapping[str, Any]) -> str:
    """Identify a cadastral disposition without including its sale value."""
    fields = ("date_mutation", "insee_code", "no_disposition", "code_departement",
              "prefixe_section", "section", "no_plan")
    missing = [field for field in fields[:3] if row.get(field) in (None, "")]
    if missing:
        raise ValueError(f"Cannot build mutation key; missing {', '.join(missing)}")
    parcel = tuple(_text(row.get(field) or "") for field in fields[3:])
    parts = [_text(row[field]) for field in fields[:3]] + list(parcel)
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
