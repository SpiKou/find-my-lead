"""Εξαγωγή της διοικητικής διαίρεσης της Ελλάδας από τα Overture divisions.

Γράφει δύο αρχεία στο data/raw:
    counties_gr_<release>.parquet    332 πολύγωνα δήμων, με την περιφέρεια του καθενός
    localities_gr_<release>.parquet  σημεία οικισμών (πόλη, κωμόπολη, χωριό, οικισμός)

Χρήση:
    uv run python pipeline/extract_divisions.py [--release 2026-10-21.0]
"""

import argparse
import time
from pathlib import Path

import duckdb

from extract_places import latest_release

BASE = "s3://overturemaps-us-west-2/release/{release}/theme=divisions/type={type}/*"
OUT_DIR = Path("data/raw")


def extract(release: str) -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counties_out = OUT_DIR / f"counties_gr_{release}.parquet"
    localities_out = OUT_DIR / f"localities_gr_{release}.parquet"

    areas = BASE.format(release=release, type="division_area")
    points = BASE.format(release=release, type="division")

    con = duckdb.connect()
    con.sql("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial;")
    con.sql("SET s3_region='us-west-2';")

    con.sql(f"""
        CREATE TABLE division_points AS
        SELECT id, names.primary AS name, subtype, class, population, hierarchies, geometry
        FROM read_parquet('{points}', hive_partitioning=1)
        WHERE country = 'GR' AND subtype IN ('county', 'locality')
    """)

    # Η περιφέρεια κάθε δήμου βγαίνει από την ιεραρχία του σημείου του δήμου.
    con.sql(f"""
        COPY (
            SELECT
                a.division_id                                   AS county_id,
                a.names.primary                                 AS county,
                list_filter(p.hierarchies[1], lambda h: h.subtype = 'region')[1].name AS region,
                a.geometry
            FROM read_parquet('{areas}', hive_partitioning=1) a
            JOIN division_points p ON p.id = a.division_id
            WHERE a.country = 'GR' AND a.subtype = 'county' AND a.class = 'land'
        ) TO '{counties_out}' (FORMAT parquet, COMPRESSION zstd)
    """)

    con.sql(f"""
        COPY (
            SELECT
                id                                              AS locality_id,
                name                                            AS locality,
                class                                           AS locality_class,
                population,
                list_filter(hierarchies[1], lambda h: h.subtype = 'county')[1].division_id AS county_id,
                ST_X(geometry)                                  AS lon,
                ST_Y(geometry)                                  AS lat
            FROM division_points
            WHERE subtype = 'locality'
        ) TO '{localities_out}' (FORMAT parquet, COMPRESSION zstd)
    """)
    return counties_out, localities_out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", help="π.χ. 2026-10-21.0 (default: το τελευταίο)")
    args = parser.parse_args()

    release = args.release or latest_release()
    print(f"Overture release: {release}")

    started = time.time()
    for out in extract(release):
        rows = duckdb.sql(f"SELECT count(*) FROM '{out}'").fetchall()[0][0]
        print(f"{rows:,} εγγραφές -> {out}")
    print(f"({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
