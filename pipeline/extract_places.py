"""Εξαγωγή των Overture Places για την Ελλάδα σε τοπικό parquet.

Χρήση:
    uv run python pipeline/extract_places.py               # τελευταίο release
    uv run python pipeline/extract_places.py --release 2026-10-21.0
"""

import argparse
import time
from pathlib import Path

import duckdb
import httpx

CATALOG_URL = "https://stac.overturemaps.org/catalog.json"
PLACES_PATH = "s3://overturemaps-us-west-2/release/{release}/theme=places/type=place/*"

# Bounding box της Ελλάδας (με τα νησιά). Πιάνει και κομμάτια γειτονικών
# χωρών, γι' αυτό φιλτράρουμε μετά και με τη χώρα της διεύθυνσης.
GR_BBOX = {"xmin": 19.2, "xmax": 29.8, "ymin": 34.6, "ymax": 41.9}

OUT_DIR = Path("data/raw")


def latest_release() -> str:
    return httpx.get(CATALOG_URL, timeout=30).json()["latest"]


def extract(release: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"places_gr_{release}.parquet"

    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
    con.sql("SET s3_region='us-west-2';")

    # Κρατάμε τις εγγραφές με διεύθυνση στην Ελλάδα ή χωρίς χώρα καθόλου.
    # Οι δεύτερες θα ξεκαθαρίσουν στο βήμα point-in-polygon με τα divisions.
    con.sql(f"""
        COPY (
            SELECT
                id,
                names.primary                      AS name,
                ST_X(geometry)                     AS lon,
                ST_Y(geometry)                     AS lat,
                confidence,
                operating_status,
                basic_category,
                taxonomy.primary                   AS category,
                taxonomy.hierarchy                 AS category_hierarchy,
                websites,
                emails,
                phones,
                socials,
                brand.names.primary                AS brand,
                addresses,
                sources,
                version
            FROM read_parquet('{PLACES_PATH.format(release=release)}', hive_partitioning=1)
            WHERE bbox.xmin BETWEEN {GR_BBOX['xmin']} AND {GR_BBOX['xmax']}
              AND bbox.ymin BETWEEN {GR_BBOX['ymin']} AND {GR_BBOX['ymax']}
              AND (
                    list_contains(list_transform(addresses, lambda a: a.country), 'GR')
                    OR addresses IS NULL
                    OR len(list_filter(addresses, lambda a: a.country IS NOT NULL)) = 0
              )
        ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)
    """)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", help="π.χ. 2026-10-21.0 (default: το τελευταίο)")
    args = parser.parse_args()

    release = args.release or latest_release()
    print(f"Overture release: {release}")

    started = time.time()
    out = extract(release)
    rows = duckdb.sql(f"SELECT count(*) FROM '{out}'").fetchall()[0][0]
    print(f"{rows:,} εγγραφές -> {out} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
