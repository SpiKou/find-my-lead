"""Lighthouse scores των ενεργών websites μέσω του PageSpeed Insights API.

Για κάθε site κρατά τα 4 scores (Performance, Accessibility, Best Practices,
SEO, σε κινητό) στον πίνακα lighthouse_checks και τα περνά στις επιχειρήσεις.
Όπως στο LeadCatalog, «τεχνικές αδυναμίες» σημαίνει Performance, Accessibility
ή Best Practices κάτω από 60 και «χαμηλό SEO» σημαίνει SEO κάτω από 60.

Το δωρεάν όριο της Google είναι 30 έλεγχοι το λεπτό και 25.000 την ημέρα,
οπότε ο πλήρης έλεγχος γίνεται σε δόσεις (--limit, --max-minutes).

Χρήση:
    DATABASE_URL=... PAGESPEED_API_KEY=... uv run python pipeline/lighthouse.py --limit 24000
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timezone

import httpx
import psycopg

API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
CATEGORIES = {
    "performance": "performance",
    "accessibility": "accessibility",
    "best-practices": "best_practices",
    "seo": "seo",
}
THRESHOLD = 60
# 30 αιτήματα το λεπτό· κρατάμε περιθώριο για τις επαναλήψεις.
REQUESTS_PER_SECOND = 0.45
# Τα αιτήματα παίρνουν 20–60 δευτερόλεπτα, οπότε χρειάζονται αρκετά ταυτόχρονα.
CONCURRENCY = 40
MAX_ATTEMPTS = 6
SAVE_EVERY = 500
RECHECK_DAYS = 90

CREATE = """
    CREATE TABLE IF NOT EXISTS lighthouse_checks (
        website text PRIMARY KEY, performance int, accessibility int, best_practices int,
        seo int, error text, checked_at timestamptz
    )
"""
COLUMNS = ["website", "performance", "accessibility", "best_practices", "seo", "error", "checked_at"]


class QuotaExceeded(Exception):
    pass


def parse(data: dict) -> dict:
    """Τα scores (0–100) από την απάντηση του API, ή το σφάλμα του Lighthouse."""
    result = data.get("lighthouseResult") or {}
    error = (result.get("runtimeError") or {}).get("code")
    scores = {}
    for category, column in CATEGORIES.items():
        score = (result.get("categories") or {}).get(category, {}).get("score")
        scores[column] = round(score * 100) if score is not None else None
    if all(v is None for v in scores.values()):
        error = error or "no_scores"
    return {**scores, "error": error}


# Το πρώτο μήνυμα 429 τυπώνεται, για να φαίνεται ποιο όριο ξεπεράστηκε.
_logged_429: list[bool] = []


class Pacer:
    """Μοιράζει τα αιτήματα ομοιόμορφα στον χρόνο, μαζί με τις επαναλήψεις."""

    def __init__(self, per_second: float):
        self.interval = 1 / per_second
        self.next_slot = time.monotonic()

    async def wait(self) -> None:
        now = time.monotonic()
        slot = max(self.next_slot, now)
        self.next_slot = slot + self.interval
        if slot > now:
            await asyncio.sleep(slot - now)


async def check(client: httpx.AsyncClient, key: str, website: str, pacer: Pacer) -> dict | None:
    """Τα scores ενός site· None αν η Google δεν το δέχτηκε τώρα (ξαναμπαίνει την επόμενη φορά)."""
    params = [("url", website), ("key", key), ("strategy", "mobile")]
    params += [("category", c) for c in CATEGORIES]
    # Μόνο τα scores, όχι όλη την αναφορά (μερικά MB ανά site).
    params.append(("fields", "lighthouseResult/categories/*/score,lighthouseResult/runtimeError"))
    for attempt in range(MAX_ATTEMPTS):
        await pacer.wait()
        try:
            response = await client.get(API, params=params)
        except httpx.HTTPError:
            continue
        if response.status_code == 429:
            if "per day" in response.text.lower() or "perday" in response.text.lower():
                raise QuotaExceeded
            if not _logged_429:
                _logged_429.append(True)
                print(f"  429 από τη Google: {response.text[:600]}", flush=True)
            await asyncio.sleep(30 * (attempt + 1))
            continue
        if response.status_code >= 500 and attempt < 2:
            continue
        if response.status_code != 200:
            # Συνήθως σημαίνει ότι η Google δεν μπόρεσε να ανοίξει το site.
            return {"error": f"http_{response.status_code}"}
        return parse(response.json())
    return None


async def run(websites: list[str], key: str, on_batch, deadline: float | None) -> int:
    semaphore = asyncio.Semaphore(CONCURRENCY)
    pacer = Pacer(REQUESTS_PER_SECOND)
    pending: list[dict] = []
    done = skipped = 0
    started = time.time()
    stop = asyncio.Event()

    async def worker(website: str) -> None:
        nonlocal done, skipped
        async with semaphore:
            if stop.is_set() or (deadline and time.time() > deadline):
                return
            try:
                result = await check(client, key, website, pacer)
            except QuotaExceeded:
                if not stop.is_set():
                    print("  Τέλος του ημερήσιου ορίου της Google", flush=True)
                stop.set()
                return
            if result is None:
                skipped += 1
                return
            pending.append({"website": website, "checked_at": datetime.now(timezone.utc), **result})
            done += 1
            if done % 250 == 0:
                print(f"  {done:,}/{len(websites):,} ({done / (time.time() - started):.1f}/s)", flush=True)
            if len(pending) >= SAVE_EVERY:
                batch = pending.copy()
                pending.clear()
                await asyncio.to_thread(on_batch, batch)

    async with httpx.AsyncClient(timeout=httpx.Timeout(120, pool=None)) as client:
        await asyncio.gather(*(worker(w) for w in websites))
    if pending:
        await asyncio.to_thread(on_batch, pending)
    if skipped:
        print(f"  {skipped:,} sites δεν έγιναν δεκτά από τη Google και μένουν για την επόμενη φορά", flush=True)
    return done


def websites_to_check(conn: psycopg.Connection, limit: int, recheck_days: int) -> list[str]:
    conn.execute(CREATE)
    # Πρώτα όσα δεν ελέγχθηκαν ποτέ, μετά τα παλαιότερα.
    rows = conn.execute(
        """
        SELECT b.website FROM businesses b
        LEFT JOIN lighthouse_checks l USING (website)
        WHERE b.website_status = 'active'
          AND (l.checked_at IS NULL OR l.checked_at < now() - make_interval(days => %s)
               -- Παλιότερες απορρίψεις λόγω ορίου ή χρόνου ξαναδοκιμάζονται.
               OR l.error = 'retries' OR l.error LIKE '%%Timeout')
        GROUP BY b.website, l.checked_at
        ORDER BY l.checked_at NULLS FIRST, md5(b.website)
        LIMIT %s
        """,
        [recheck_days, limit or None],
    ).fetchall()
    return [w for (w,) in rows]


def save(conn: psycopg.Connection, results: list[dict]) -> None:
    with conn.transaction():
        conn.execute("CREATE TEMP TABLE lighthouse_new (LIKE lighthouse_checks) ON COMMIT DROP")
        with conn.cursor().copy(f"COPY lighthouse_new ({', '.join(COLUMNS)}) FROM STDIN") as copy:
            for r in results:
                copy.write_row([r.get(c) for c in COLUMNS])
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c != "website")
        conn.execute(f"""
            INSERT INTO lighthouse_checks SELECT * FROM lighthouse_new
            ON CONFLICT (website) DO UPDATE SET {updates}
        """)


def apply(conn: psycopg.Connection, table: str = "businesses") -> int:
    """Περνά τα scores στις επιχειρήσεις· επιστρέφει πόσες άλλαξαν."""
    conn.execute(CREATE)
    cursor = conn.execute(f"""
        UPDATE {table} b SET
            lighthouse_performance    = l.performance,
            lighthouse_accessibility  = l.accessibility,
            lighthouse_best_practices = l.best_practices,
            lighthouse_seo            = l.seo,
            has_technical_weaknesses  = LEAST(l.performance, l.accessibility, l.best_practices) < {THRESHOLD},
            has_low_seo               = l.seo < {THRESHOLD}
        FROM lighthouse_checks l
        WHERE b.website = l.website
          AND l.error IS NULL
          AND (b.lighthouse_performance, b.lighthouse_accessibility, b.lighthouse_best_practices, b.lighthouse_seo)
              IS DISTINCT FROM (l.performance, l.accessibility, l.best_practices, l.seo)
    """)
    return cursor.rowcount


def report(conn: psycopg.Connection) -> None:
    conn.execute(CREATE)
    print("Σφάλματα:", conn.execute(
        "SELECT coalesce(error, 'ok'), count(*) FROM lighthouse_checks GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall())
    print("Επιχειρήσεις:", conn.execute(
        "SELECT count(*) FILTER (WHERE lighthouse_performance IS NOT NULL),"
        " count(*) FILTER (WHERE has_technical_weaknesses), count(*) FILTER (WHERE has_low_seo)"
        " FROM businesses"
    ).fetchone())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=24000, help="πόσα sites το πολύ (0 = όλα)")
    parser.add_argument("--recheck-days", type=int, default=RECHECK_DAYS)
    parser.add_argument("--max-minutes", type=float, help="μετά από τόσα λεπτά δεν ξεκινά νέα sites")
    parser.add_argument("--report", action="store_true", help="μόνο σύνοψη των ελέγχων που έχουν γίνει")
    args = parser.parse_args()

    url, key = os.environ.get("DATABASE_URL"), os.environ.get("PAGESPEED_API_KEY")
    if not url or (not key and not args.report):
        sys.exit("Λείπει το DATABASE_URL ή το PAGESPEED_API_KEY")

    with psycopg.connect(url, autocommit=True) as conn:
        if args.report:
            report(conn)
            return
        websites = websites_to_check(conn, args.limit, args.recheck_days)
    print(f"{len(websites):,} sites για Lighthouse")

    totals = {"saved": 0, "errors": 0}

    def save_batch(batch: list[dict]) -> None:
        with psycopg.connect(url, autocommit=True) as conn:
            save(conn, batch)
            updated = apply(conn)
        totals["saved"] += len(batch)
        totals["errors"] += sum(1 for r in batch if r.get("error"))
        print(f"  Αποθηκεύτηκαν {len(batch):,} sites, {updated:,} επιχειρήσεις ενημερώθηκαν", flush=True)

    started = time.time()
    deadline = started + args.max_minutes * 60 if args.max_minutes else None
    asyncio.run(run(websites, key, save_batch, deadline))
    print(f"{totals['saved']:,} sites σε {time.time() - started:.0f}s, {totals['errors']:,} χωρίς scores")


if __name__ == "__main__":
    main()
