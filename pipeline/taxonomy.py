"""Φόρτωση και έλεγχος του πίνακα κλάδων και κατηγοριών (pipeline/taxonomy/*.csv).

Τα CSV είναι η μοναδική πηγή αλήθειας για τους κλάδους και διορθώνονται με
το χέρι. Η αντιστοίχιση ψάχνει πρώτα την αναλυτική κατηγορία του Overture
(taxonomy.primary) και μετά τη βασική (basic_category).
"""

import csv
from pathlib import Path

import duckdb

TAXONOMY_DIR = Path(__file__).resolve().parent / "taxonomy"
ENTITY_TYPES = {"business", "organization", "public", "place", "infrastructure"}

# Για εγγραφές χωρίς κατηγορία στο Overture.
UNCATEGORIZED_NAME_EL = "Χωρίς σαφή κατηγορία"


def _read(name: str) -> list[dict[str, str]]:
    with open(TAXONOMY_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate() -> list[str]:
    """Επιστρέφει λίστα με τα προβλήματα των CSV (κενή αν όλα είναι εντάξει)."""
    errors = []
    industries = {r["slug"] for r in _read("industries.csv")}
    types = _read("business_types.csv")
    type_slugs = {r["slug"] for r in types}
    mapping = _read("category_map.csv")

    if len(type_slugs) != len(types):
        errors.append("business_types.csv: διπλό slug")
    for r in types:
        if r["industry"] not in industries:
            errors.append(f"business_types.csv: άγνωστος κλάδος '{r['industry']}' στο '{r['slug']}'")

    seen = set()
    for r in mapping:
        cat = r["overture_category"]
        if cat in seen:
            errors.append(f"category_map.csv: διπλή κατηγορία '{cat}'")
        seen.add(cat)
        if r["entity_type"] not in ENTITY_TYPES:
            errors.append(f"category_map.csv: άγνωστο entity_type '{r['entity_type']}' στο '{cat}'")
        if r["entity_type"] == "business" and r["business_type"] not in type_slugs:
            errors.append(f"category_map.csv: άγνωστος τύπος '{r['business_type']}' στο '{cat}'")
        if r["entity_type"] != "business" and r["business_type"]:
            errors.append(f"category_map.csv: το '{cat}' δεν είναι business αλλά έχει τύπο")
    return errors


def load(con: duckdb.DuckDBPyConnection) -> None:
    """Φορτώνει τα CSV ως πίνακες taxonomy_industries, taxonomy_types, taxonomy_map."""
    errors = validate()
    if errors:
        raise ValueError("Προβλήματα στα taxonomy CSV:\n" + "\n".join(errors))
    for table, name in [
        ("taxonomy_industries", "industries.csv"),
        ("taxonomy_types", "business_types.csv"),
        ("taxonomy_map", "category_map.csv"),
    ]:
        con.sql(f"""
            CREATE TABLE {table} AS
            SELECT * FROM read_csv('{TAXONOMY_DIR / name}', header = true, all_varchar = true)
        """)
