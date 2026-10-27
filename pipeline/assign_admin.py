"""Αντιστοίχιση κάθε επιχείρησης σε περιφέρεια, δήμο και οικισμό.

- Δήμος: το πολύγωνο δήμου που περιέχει το σημείο. Αν δεν πέφτει σε κανένα
  (π.χ. σε προβλήτα ή λίγο μέσα στη θάλασσα), ο πλησιέστερος δήμος έως
  MAX_NEAREST_DEG. Πιο μακριά θεωρείται εκτός Ελλάδας και αφαιρείται.
- Περιφέρεια: από τον δήμο.
- Οικισμός: ο οικισμός του ίδιου δήμου με τη μικρότερη απόσταση ζυγισμένη
  με το μέγεθός του (LOCALITY_RADIUS_KM), ώστε ένα κατάστημα στο κέντρο των
  Χανίων να μη βγαίνει σε ένα γειτονικό χωριουδάκι.

Διαβάζει τα αρχεία των extract_places.py και extract_divisions.py και γράφει
data/staging/places_admin_<release>.parquet.

Χρήση:
    uv run python pipeline/assign_admin.py [--release 2026-10-21.0]
"""

import argparse
import time
from pathlib import Path

import duckdb

from extract_places import latest_release

RAW_DIR = Path("data/raw")
OUT_DIR = Path("data/staging")

# ~5 km στο γεωγραφικό πλάτος της Ελλάδας.
MAX_NEAREST_DEG = 0.05

# Πόσο μακριά «τραβάει» κάθε τύπος οικισμού. Η απόσταση διαιρείται με αυτό.
LOCALITY_RADIUS_KM = {
    "city": 6.0,
    "town": 2.5,
    "macrohood": 2.5,
    "village": 1.0,
    "hamlet": 0.5,
}


def assign(release: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"places_admin_{release}.parquet"

    con = duckdb.connect()
    con.sql("INSTALL spatial; LOAD spatial;")
    con.sql(f"CREATE TABLE places AS SELECT * FROM '{RAW_DIR}/places_gr_{release}.parquet'")
    con.sql(f"CREATE TABLE counties AS SELECT * FROM '{RAW_DIR}/counties_gr_{release}.parquet'")
    con.sql(f"CREATE TABLE localities AS SELECT * FROM '{RAW_DIR}/localities_gr_{release}.parquet'")

    con.sql("""
        CREATE TABLE inside AS
        SELECT p.id, c.county_id, 0.0 AS distance_deg
        FROM places p
        JOIN counties c ON ST_Contains(c.geometry, ST_Point(p.lon, p.lat))
    """)

    # Σπάνια ένα σημείο πέφτει πάνω σε όριο δύο δήμων. Κρατάμε έναν.
    con.sql("""
        CREATE TABLE inside_one AS
        SELECT id, any_value(county_id) AS county_id, 0.0 AS distance_deg
        FROM inside GROUP BY id
    """)

    con.sql(f"""
        CREATE TABLE nearest AS
        SELECT p.id,
               arg_min(c.county_id, ST_Distance(c.geometry, ST_Point(p.lon, p.lat))) AS county_id,
               min(ST_Distance(c.geometry, ST_Point(p.lon, p.lat)))                AS distance_deg
        FROM places p
        JOIN counties c
          ON ST_DWithin(c.geometry, ST_Point(p.lon, p.lat), {MAX_NEAREST_DEG})
        WHERE p.id NOT IN (SELECT id FROM inside_one)
        GROUP BY p.id
    """)

    con.sql("""
        CREATE TABLE place_county AS
        SELECT id, county_id, 'inside' AS admin_match FROM inside_one
        UNION ALL
        SELECT id, county_id, 'nearest' FROM nearest
    """)

    radius_cases = " ".join(f"WHEN '{k}' THEN {v}" for k, v in LOCALITY_RADIUS_KM.items())

    # Απόσταση σε km με προσέγγιση ισοορθογώνιας προβολής (1° ≈ 111 km,
    # cos 38° ≈ 0.79 για το γεωγραφικό μήκος). Αρκεί για σύγκριση αποστάσεων.
    con.sql(f"""
        CREATE TABLE place_locality AS
        WITH scored AS (
            SELECT p.id, l.locality, l.locality_class,
                   111 * sqrt(pow((l.lon - p.lon) * 0.79, 2) + pow(l.lat - p.lat, 2))
                     / CASE l.locality_class {radius_cases} ELSE 1.0 END AS score
            FROM places p
            JOIN place_county pc ON pc.id = p.id
            JOIN localities l ON l.county_id = pc.county_id
        )
        SELECT id,
               arg_min(locality, score)       AS locality,
               arg_min(locality_class, score) AS locality_class
        FROM scored
        GROUP BY id
    """)

    con.sql(f"""
        COPY (
            SELECT p.*,
                   c.region,
                   c.county,
                   pl.locality,
                   pl.locality_class,
                   pc.admin_match
            FROM places p
            JOIN place_county pc ON pc.id = p.id
            JOIN counties c ON c.county_id = pc.county_id
            LEFT JOIN place_locality pl ON pl.id = p.id
        ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
    """)

    total = con.sql("SELECT count(*) FROM places").fetchall()[0][0]
    kept = con.sql("SELECT count(*) FROM place_county").fetchall()[0][0]
    by_match = con.sql("SELECT admin_match, count(*) FROM place_county GROUP BY 1 ORDER BY 1").fetchall()
    print(f"{total:,} επιχειρήσεις, {kept:,} αντιστοιχίστηκαν, {total - kept:,} εκτός Ελλάδας")
    for match, count in by_match:
        print(f"  {match}: {count:,}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", help="π.χ. 2026-10-21.0 (default: το τελευταίο)")
    args = parser.parse_args()

    release = args.release or latest_release()
    print(f"Overture release: {release}")

    started = time.time()
    out = assign(release)
    print(f"-> {out} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
