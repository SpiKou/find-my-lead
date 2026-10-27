"""Ο πίνακας site_checks της βάσης και η εφαρμογή του στις επιχειρήσεις.

Το crawl (crawl_sites.py) γράφει ένα αποτέλεσμα ανά website. Από εκεί
συμπληρώνονται στις επιχειρήσεις η κατάσταση website, οι τεχνολογίες, το e-shop
και τα emails/socials που βρέθηκαν στο site. Εφαρμόζεται μετά από κάθε crawl
και κάθε φόρτωση (load_db.py), ώστε τα αποτελέσματα να μη χάνονται.
"""

import psycopg

CREATE = """
    CREATE TABLE IF NOT EXISTS site_checks (
        website text PRIMARY KEY, status text, reason text, http_status int, final_url text,
        emails text[], socials text[], social_platforms text[], technologies text[],
        eshop boolean, checked_at timestamptz
    )
"""


def _union(column: str) -> str:
    return f"ARRAY(SELECT DISTINCT x FROM unnest(b.{column} || c.{column}::varchar[]) x ORDER BY x)"


def apply(conn: psycopg.Connection, table: str = "businesses") -> int:
    """Ενημερώνει τον πίνακα επιχειρήσεων από το site_checks· επιστρέφει πόσες άλλαξαν."""
    conn.execute(CREATE)
    cursor = conn.execute(f"""
        UPDATE {table} b SET
            website_status   = c.status,
            technologies     = c.technologies::varchar[],
            eshop            = c.eshop,
            emails           = {_union("emails")},
            socials          = {_union("socials")},
            social_platforms = {_union("social_platforms")},
            has_email        = cardinality(b.emails) + cardinality(c.emails) > 0,
            has_social       = cardinality(b.socials) + cardinality(c.socials) > 0
        FROM site_checks c
        WHERE b.website = c.website
          AND (
            b.website_status IS DISTINCT FROM c.status
            OR b.technologies IS DISTINCT FROM c.technologies::varchar[]
            OR b.eshop IS DISTINCT FROM c.eshop
            OR NOT c.emails::varchar[] <@ b.emails
            OR NOT c.socials::varchar[] <@ b.socials
          )
    """)
    return cursor.rowcount
