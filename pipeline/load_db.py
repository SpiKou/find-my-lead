"""Φόρτωση των επιχειρήσεων και των κλάδων στη βάση Postgres (Neon).

Γράφει πρώτα σε προσωρινούς πίνακες και μετά, μέσα σε ένα transaction,
αντικαθιστά τους παλιούς. Το site δεν βλέπει ποτέ μισοφορτωμένα δεδομένα.

Χρήση:
    DATABASE_URL=postgres://... uv run python pipeline/load_db.py [--release 2026-10-21.0]
"""

import argparse
import os
import sys
import time
from pathlib import Path

import duckdb
import psycopg

import normalize as n
import taxonomy
from extract_places import latest_release

STAGING_DIR = Path("data/staging")

# Indexes για τα φίλτρα του docs/filters.md και την αναζήτηση ονόματος.
INDEXES = [
    "CREATE INDEX businesses_industry_idx ON businesses (industry)",
    "CREATE INDEX businesses_business_type_idx ON businesses (business_type)",
    "CREATE INDEX businesses_website_status_idx ON businesses (website_status)",
    "CREATE INDEX businesses_admin_areas_idx ON businesses USING gin (administrative_areas)",
    "CREATE INDEX businesses_localities_idx ON businesses USING gin (localities)",
    "CREATE INDEX businesses_technologies_idx ON businesses USING gin (technologies)",
    "CREATE INDEX businesses_search_name_idx ON businesses USING gin (search_name gin_trgm_ops)",
    "CREATE INDEX businesses_name_idx ON businesses (name)",
]


def stage(con: duckdb.DuckDBPyConnection, release: str) -> None:
    """Γράφει τους πίνακες *_staging στη βάση μέσω της επέκτασης postgres του DuckDB."""
    con.create_function("name_search", n.name_search, ["VARCHAR"], "VARCHAR", null_handling="special")
    taxonomy.load(con)

    for table in ["businesses_staging", "industries_staging", "business_types_staging", "dataset_staging"]:
        con.sql(f"DROP TABLE IF EXISTS pg.public.{table}")

    con.sql(f"""
        CREATE TABLE pg.public.businesses_staging AS
        SELECT
            substr(md5(business_key), 1, 12)    AS id,
            business_key,
            name,
            name_search(name)                   AS search_name,
            business_type,
            business_type_name,
            industry,
            industry_name,
            brand,
            website,
            website_status,
            emails,
            phones,
            socials,
            social_platforms,
            has_email,
            has_phone,
            has_social,
            locations,
            localities,
            counties,
            administrative_areas,
            locations_count::INTEGER            AS locations_count,
            technologies,
            eshop,
            lighthouse_performance,
            lighthouse_accessibility,
            lighthouse_best_practices,
            lighthouse_seo,
            has_technical_weaknesses,
            has_low_seo,
            confidence
        FROM '{STAGING_DIR}/businesses_{release}.parquet'
    """)
    con.sql("CREATE TABLE pg.public.industries_staging AS SELECT slug, name_el FROM taxonomy_industries")
    con.sql("CREATE TABLE pg.public.business_types_staging AS SELECT slug, name_el, industry FROM taxonomy_types")
    con.sql(f"""
        CREATE TABLE pg.public.dataset_staging AS
        SELECT '{release}' AS overture_release, now() AS loaded_at
    """)


def swap(conn: psycopg.Connection) -> None:
    """Αντικαθιστά τους παλιούς πίνακες με τους staging μέσα σε ένα transaction."""
    with conn.transaction():
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        for table in ["businesses", "industries", "business_types", "dataset"]:
            conn.execute(f"DROP TABLE IF EXISTS {table}")
            conn.execute(f"ALTER TABLE {table}_staging RENAME TO {table}")
        conn.execute("ALTER TABLE businesses ADD PRIMARY KEY (id)")
        conn.execute("ALTER TABLE industries ADD PRIMARY KEY (slug)")
        conn.execute("ALTER TABLE business_types ADD PRIMARY KEY (slug)")
        for statement in INDEXES:
            conn.execute(statement)
    conn.execute("ANALYZE businesses")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", help="π.χ. 2026-10-21.0 (default: το τελευταίο)")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Λείπει το DATABASE_URL")

    release = args.release or latest_release()
    print(f"Overture release: {release}")
    started = time.time()

    con = duckdb.connect()
    con.sql("INSTALL postgres; LOAD postgres;")
    con.execute("ATTACH ? AS pg (TYPE postgres)", [url])
    stage(con, release)
    con.sql("DETACH pg")

    with psycopg.connect(url, autocommit=True) as conn:
        swap(conn)
        rows = conn.execute("SELECT count(*) FROM businesses").fetchone()[0]
        size = conn.execute("SELECT pg_size_pretty(pg_database_size(current_database()))").fetchone()[0]

    print(f"{rows:,} επιχειρήσεις στη βάση, μέγεθος βάσης {size} ({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
