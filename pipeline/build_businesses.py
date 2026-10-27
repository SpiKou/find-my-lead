"""Κανονικοποίηση, φιλτράρισμα θορύβου, dedupe και ομαδοποίηση σε επιχειρήσεις.

Διαβάζει data/staging/places_admin_<release>.parquet και γράφει:
    data/staging/locations_<release>.parquet   μία γραμμή ανά φυσική τοποθεσία
    data/staging/businesses_<release>.parquet  μία γραμμή ανά επιχείρηση
                                               (μια αλυσίδα = μία επιχείρηση
                                               με πολλές τοποθεσίες)

Χρήση:
    uv run python pipeline/build_businesses.py [--release 2026-10-21.0]
"""

import argparse
import time
from pathlib import Path

import duckdb

import normalize as n
from extract_places import latest_release

STAGING_DIR = Path("data/staging")

# Κάτω από αυτό το Overture confidence η εγγραφή συνήθως είναι λάθος ή ανενεργή.
MIN_CONFIDENCE = 0.4

# Δύο εγγραφές με το ίδιο όνομα σε απόσταση έως τόσα μέτρα είναι το ίδιο σημείο.
DUPLICATE_RADIUS_M = 150

# Ένα domain δεν ενώνει τοποθεσίες όταν σχεδόν κάθε τοποθεσία του έχει άλλο
# όνομα: τότε είναι πλατφόρμα ή hosting, όχι αλυσίδα. Μια αλυσίδα έχει λίγες
# παραλλαγές ονόματος (π.χ. "Alpha Bank" / "ATM Alpha Bank" σε 860 τοποθεσίες).
SHARED_SITE_MIN_LOCATIONS = 3
SHARED_SITE_MAX_DISTINCT_NAME_RATIO = 0.5


def register_udfs(con: duckdb.DuckDBPyConnection) -> None:
    str_fns = {
        "norm_phone": n.normalize_phone,
        "phone_type": n.phone_type,
        "norm_website": n.normalize_website,
        "website_kind": n.website_kind,
        "site_key": n.site_key,
        "norm_email": n.normalize_email,
        "social_platform": n.social_platform,
        "name_key": n.name_key,
    }
    for name, fn in str_fns.items():
        con.create_function(name, fn, ["VARCHAR"], "VARCHAR", null_handling="special")
    con.create_function("is_free_email", n.is_free_email, ["VARCHAR"], "BOOLEAN", null_handling="special")
    con.create_function("is_junk_name", n.is_junk_name, ["VARCHAR"], "BOOLEAN", null_handling="special")


def normalize_contacts(con: duckdb.DuckDBPyConnection) -> None:
    """Κανονικοποιεί τις λίστες επικοινωνίας. Οι UDF τρέχουν μόνο στις μοναδικές τιμές."""
    con.sql("""
        CREATE TABLE phone_map AS
        SELECT raw, norm_phone(raw) AS phone
        FROM (SELECT DISTINCT unnest(phones) AS raw FROM places)
    """)
    con.sql("""
        CREATE TABLE website_map AS
        SELECT raw, norm_website(raw) AS website, website_kind(raw) AS kind, site_key(raw) AS site_key
        FROM (SELECT DISTINCT unnest(websites) AS raw FROM places)
    """)
    con.sql("""
        CREATE TABLE email_map AS
        SELECT raw, norm_email(raw) AS email
        FROM (SELECT DISTINCT unnest(emails) AS raw FROM places)
    """)
    con.sql("""
        CREATE TABLE social_map AS
        SELECT raw, social_platform(raw) AS platform
        FROM (SELECT DISTINCT unnest(socials) AS raw FROM places)
    """)

    con.sql("""
        CREATE TABLE contacts AS
        WITH
        ph AS (
            SELECT id, list(DISTINCT m.phone) FILTER (WHERE m.phone IS NOT NULL) AS phones
            FROM (SELECT id, unnest(phones) AS raw FROM places) JOIN phone_map m USING (raw)
            GROUP BY id
        ),
        we AS (
            SELECT id,
                   list(DISTINCT m.website) FILTER (WHERE m.kind = 'own')     AS own_websites,
                   list(DISTINCT m.site_key) FILTER (WHERE m.kind = 'own')    AS site_keys,
                   list(DISTINCT m.website) FILTER (WHERE m.kind <> 'own')    AS other_websites
            FROM (SELECT id, unnest(websites) AS raw FROM places) JOIN website_map m USING (raw)
            GROUP BY id
        ),
        em AS (
            SELECT id, list(DISTINCT m.email) FILTER (WHERE m.email IS NOT NULL) AS emails
            FROM (SELECT id, unnest(emails) AS raw FROM places) JOIN email_map m USING (raw)
            GROUP BY id
        ),
        so AS (
            SELECT id, list(DISTINCT s.raw) FILTER (WHERE m.platform IS NOT NULL) AS socials
            FROM (SELECT id, unnest(socials) AS raw FROM places) s JOIN social_map m USING (raw)
            GROUP BY id
        )
        SELECT p.id,
               coalesce(ph.phones, [])          AS phones,
               coalesce(we.own_websites, [])    AS own_websites,
               coalesce(we.site_keys, [])       AS site_keys,
               -- Social/πλατφόρμες που είχαν δηλωθεί ως website πάνε μαζί με τα socials.
               list_distinct(coalesce(so.socials, []) || coalesce(we.other_websites, [])) AS socials,
               coalesce(em.emails, [])          AS emails
        FROM places p
        LEFT JOIN ph USING (id)
        LEFT JOIN we USING (id)
        LEFT JOIN em USING (id)
        LEFT JOIN so USING (id)
    """)


def filter_and_dedupe(con: duckdb.DuckDBPyConnection) -> None:
    con.sql(f"""
        CREATE TABLE kept AS
        SELECT p.id, p.name, name_key(p.name) AS name_key, p.lon, p.lat, p.confidence,
               p.basic_category, p.category, p.category_hierarchy, p.brand,
               p.region, p.county, p.locality, p.sources,
               c.phones, c.own_websites, c.site_keys, c.socials, c.emails
        FROM places p
        JOIN contacts c USING (id)
        WHERE NOT is_junk_name(p.name)
          AND coalesce(p.operating_status, '') <> 'permanently_closed'
          AND p.confidence >= {MIN_CONFIDENCE}
    """)

    # Κάθε εγγραφή δείχνει στην πιο αξιόπιστη εγγραφή με το ίδιο όνομα κοντά της
    # (ή στον εαυτό της). Αυτή γίνεται η "κύρια" και απορροφά τα στοιχεία των άλλων.
    con.sql(f"""
        CREATE TABLE dup_rep AS
        SELECT a.id, arg_max(b.id, (b.confidence, b.id)) AS rep_id
        FROM kept a
        JOIN kept b
          ON a.name_key = b.name_key
         AND a.county = b.county
         AND 111000 * sqrt(pow((a.lon - b.lon) * 0.79, 2) + pow(a.lat - b.lat, 2)) <= {DUPLICATE_RADIUS_M}
        GROUP BY a.id
    """)

    con.sql("""
        CREATE TABLE locations AS
        SELECT r.rep_id                                       AS id,
               any_value(k.name) FILTER (WHERE k.id = r.rep_id)            AS name,
               any_value(k.name_key) FILTER (WHERE k.id = r.rep_id)        AS name_key,
               any_value(k.lon) FILTER (WHERE k.id = r.rep_id)             AS lon,
               any_value(k.lat) FILTER (WHERE k.id = r.rep_id)             AS lat,
               max(k.confidence)                                           AS confidence,
               any_value(k.basic_category) FILTER (WHERE k.id = r.rep_id)  AS basic_category,
               any_value(k.category) FILTER (WHERE k.id = r.rep_id)        AS category,
               any_value(k.category_hierarchy) FILTER (WHERE k.id = r.rep_id) AS category_hierarchy,
               any_value(k.brand) FILTER (WHERE k.brand IS NOT NULL)       AS brand,
               any_value(k.region) FILTER (WHERE k.id = r.rep_id)          AS region,
               any_value(k.county) FILTER (WHERE k.id = r.rep_id)          AS county,
               any_value(k.locality) FILTER (WHERE k.id = r.rep_id)        AS locality,
               list_distinct(flatten(list(k.phones)))                      AS phones,
               list_distinct(flatten(list(k.own_websites)))                AS own_websites,
               list_distinct(flatten(list(k.site_keys)))                   AS site_keys,
               list_distinct(flatten(list(k.socials)))                     AS socials,
               list_distinct(flatten(list(k.emails)))                      AS emails,
               list(k.id)                                                  AS overture_ids
        FROM kept k
        JOIN dup_rep r USING (id)
        GROUP BY r.rep_id
    """)


def group_businesses(con: duckdb.DuckDBPyConnection) -> None:
    con.sql(f"""
        CREATE TABLE shared_sites AS
        SELECT site_keys[1] AS site_key
        FROM locations
        WHERE site_keys[1] IS NOT NULL
        GROUP BY 1
        HAVING count(*) >= {SHARED_SITE_MIN_LOCATIONS}
           AND count(DISTINCT name_key) / count(*) >= {SHARED_SITE_MAX_DISTINCT_NAME_RATIO}
    """)

    con.sql("""
        CREATE TABLE location_site AS
        SELECT l.*,
               CASE WHEN l.site_keys[1] NOT IN (SELECT site_key FROM shared_sites)
                    THEN l.site_keys[1] END AS own_site_key
        FROM locations l
    """)

    # Ενώνουμε ένα brand με ένα domain, ώστε π.χ. οι 858 τοποθεσίες με brand
    # "Εθνική Τράπεζα" χωρίς website να πάνε μαζί με τις 472 του nbg.gr.
    # Δύο τρόποι, με προτεραιότητα στον πρώτο:
    #   1. Το όνομα που επικρατεί στο brand είναι το ίδιο με αυτό του domain.
    #   2. Το domain εμφανίζεται σε αρκετές τοποθεσίες του brand.
    con.sql("""
        CREATE TABLE site_name AS
        SELECT own_site_key AS site_key, mode(name_key) AS name_key, count(*) AS n
        FROM location_site
        WHERE own_site_key IS NOT NULL
        GROUP BY 1
        HAVING count(*) >= 3
    """)
    con.sql("""
        CREATE TABLE brand_site AS
        WITH brand_name AS (
            SELECT name_key(brand) AS brand_key, mode(name_key) AS name_key
            FROM location_site WHERE brand IS NOT NULL GROUP BY 1
        ),
        by_name AS (
            SELECT b.brand_key, arg_max(s.site_key, s.n) AS site_key
            FROM brand_name b JOIN site_name s USING (name_key)
            GROUP BY 1
        ),
        by_support AS (
            SELECT brand_key, site_key
            FROM (
                SELECT name_key(brand) AS brand_key, own_site_key AS site_key,
                       count(*) AS n, sum(count(*)) OVER (PARTITION BY name_key(brand)) AS total
                FROM location_site
                WHERE brand IS NOT NULL AND own_site_key IS NOT NULL
                GROUP BY 1, 2
            )
            WHERE n >= 3 AND n / total >= 0.6
        )
        SELECT brand_key, coalesce(bn.site_key, bs.site_key) AS site_key
        FROM by_name bn FULL JOIN by_support bs USING (brand_key)
    """)

    con.sql("""
        CREATE TABLE location_business AS
        SELECT l.* EXCLUDE (own_site_key),
               CASE
                   WHEN l.own_site_key IS NOT NULL         THEN 'site:' || l.own_site_key
                   WHEN bs.site_key IS NOT NULL            THEN 'site:' || bs.site_key
                   WHEN name_key(l.brand) IS NOT NULL      THEN 'brand:' || name_key(l.brand)
                   WHEN l.phones[1] IS NOT NULL AND l.name_key IS NOT NULL
                                                           THEN 'phone:' || l.phones[1] || '|' || l.name_key
                   ELSE 'place:' || l.id
               END AS business_key
        FROM location_site l
        LEFT JOIN brand_site bs ON bs.brand_key = name_key(l.brand)
    """)

    con.sql("""
        CREATE TABLE businesses AS
        SELECT business_key,
               mode(name)                                         AS name,
               mode(basic_category)                               AS basic_category,
               mode(category)                                     AS category,
               any_value(brand)                                   AS brand,
               -- Το πιο συχνό δικό τους website της ομάδας.
               mode(own_websites[1]) FILTER (WHERE len(own_websites) > 0) AS website,
               list_distinct(flatten(list(emails)))               AS emails,
               list_distinct(flatten(list(phones)))               AS phones,
               list_distinct(flatten(list(socials)))              AS socials,
               count(*)                                           AS locations_count,
               list_distinct(list(locality || ', ' || region))    AS locations,
               list_distinct(list(locality))                      AS localities,
               list_distinct(list(county))                        AS counties,
               list_distinct(list(region))                        AS regions,
               max(confidence)                                    AS confidence,
               list(id)                                           AS location_ids
        FROM location_business
        GROUP BY business_key
    """)


def build(release: str) -> tuple[Path, Path]:
    locations_out = STAGING_DIR / f"locations_{release}.parquet"
    businesses_out = STAGING_DIR / f"businesses_{release}.parquet"

    con = duckdb.connect()
    register_udfs(con)
    con.sql(f"CREATE TABLE places AS SELECT * FROM '{STAGING_DIR}/places_admin_{release}.parquet'")

    normalize_contacts(con)
    filter_and_dedupe(con)
    group_businesses(con)

    con.sql(f"COPY location_business TO '{locations_out}' (FORMAT parquet, COMPRESSION zstd)")
    con.sql(f"COPY businesses TO '{businesses_out}' (FORMAT parquet, COMPRESSION zstd)")

    count = lambda table: con.sql(f"SELECT count(*) FROM {table}").fetchall()[0][0]  # noqa: E731
    print(f"{count('places'):,} εγγραφές Overture")
    print(f"{count('kept'):,} μετά το φίλτρο θορύβου (confidence >= {MIN_CONFIDENCE})")
    print(f"{count('locations'):,} τοποθεσίες μετά το dedupe")
    print(f"{count('businesses'):,} επιχειρήσεις ({count('shared_sites'):,} κοινόχρηστα domains αγνοήθηκαν)")
    return locations_out, businesses_out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", help="π.χ. 2026-10-21.0 (default: το τελευταίο)")
    args = parser.parse_args()

    release = args.release or latest_release()
    print(f"Overture release: {release}")

    started = time.time()
    for out in build(release):
        print(f"-> {out}")
    print(f"({time.time() - started:.0f}s)")


if __name__ == "__main__":
    main()
