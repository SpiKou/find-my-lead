"""Φόρτωση και έλεγχος του πίνακα κλάδων και κατηγοριών (pipeline/taxonomy/*.csv).

Τα CSV είναι η μοναδική πηγή αλήθειας για τους κλάδους και διορθώνονται με
το χέρι. Η αντιστοίχιση ψάχνει πρώτα την αναλυτική κατηγορία του Overture
(taxonomy.primary) και μετά τη βασική (basic_category).

Για εγγραφές χωρίς κατηγορία ή με γενική κατηγορία (generic_categories.csv)
εφαρμόζονται και κανόνες στο όνομα (name_rules.csv). Ο πρώτος κανόνας που
ταιριάζει κερδίζει, άρα οι πιο συγκεκριμένοι μπαίνουν πρώτοι.
"""

import csv
import re
from functools import cache
from pathlib import Path

import duckdb

from normalize import name_search

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

    for i, r in enumerate(_read("name_rules.csv"), start=2):
        try:
            re.compile(r["pattern"])
        except re.error as e:
            errors.append(f"name_rules.csv γραμμή {i}: λάθος regex ({e})")
        if r["entity_type"] not in ENTITY_TYPES:
            errors.append(f"name_rules.csv γραμμή {i}: άγνωστο entity_type '{r['entity_type']}'")
        if r["entity_type"] == "business" and r["business_type"] not in type_slugs:
            errors.append(f"name_rules.csv γραμμή {i}: άγνωστος τύπος '{r['business_type']}'")

    for r in _read("generic_categories.csv"):
        if r["overture_category"] not in seen:
            errors.append(f"generic_categories.csv: το '{r['overture_category']}' λείπει από το category_map.csv")
    return errors


@cache
def _name_rules() -> list[tuple[re.Pattern, str | None, str]]:
    # Κάθε μοτίβο ταιριάζει μόνο στην αρχή λέξης, ώστε π.χ. το "κινητ" (κινητά)
    # να μην πιάνει το "αυτοκινήτων" και το "home" να μην πιάνει το "Klimahome".
    return [
        (re.compile(rf"(?<!\w)(?:{r['pattern']})"), r["business_type"] or None, r["entity_type"])
        for r in _read("name_rules.csv")
    ]


def match_name_rule(name: str | None) -> tuple[str | None, str] | None:
    """(business_type, entity_type) από τον πρώτο κανόνα που ταιριάζει στο όνομα."""
    text = name_search(name)
    if not text:
        return None
    for pattern, business_type, entity_type in _name_rules():
        if pattern.search(text):
            return business_type, entity_type
    return None


def name_rule_udf(name: str | None) -> str | None:
    """Η match_name_rule ως 'business_type|entity_type' για χρήση ως DuckDB UDF."""
    match = match_name_rule(name)
    return f"{match[0] or ''}|{match[1]}" if match else None


def load(con: duckdb.DuckDBPyConnection) -> None:
    """Φορτώνει τα CSV ως πίνακες taxonomy_industries, taxonomy_types, taxonomy_map."""
    errors = validate()
    if errors:
        raise ValueError("Προβλήματα στα taxonomy CSV:\n" + "\n".join(errors))
    for table, name in [
        ("taxonomy_industries", "industries.csv"),
        ("taxonomy_types", "business_types.csv"),
        ("taxonomy_map", "category_map.csv"),
        ("taxonomy_generic", "generic_categories.csv"),
    ]:
        con.sql(f"""
            CREATE TABLE {table} AS
            SELECT * FROM read_csv('{TAXONOMY_DIR / name}', header = true, all_varchar = true)
        """)
