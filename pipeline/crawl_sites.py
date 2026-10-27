"""Έλεγχος των websites των επιχειρήσεων: κατάσταση, emails, socials, τεχνολογίες, e-shop.

Ανοίγει την αρχική σελίδα κάθε site και, αν δεν βρει email, τη σελίδα
επικοινωνίας. Τα αποτελέσματα γράφονται στο data/staging/site_checks.parquet και,
αν υπάρχει DATABASE_URL, στον πίνακα site_checks της βάσης, από όπου τα
παίρνει η φόρτωση των επιχειρήσεων (load_db.py).

Χρήση:
    DATABASE_URL=... uv run python pipeline/crawl_sites.py              # όσα δεν ελέγχθηκαν πρόσφατα
    DATABASE_URL=... uv run python pipeline/crawl_sites.py --sample 1000 --no-save
"""

import argparse
import asyncio
import hashlib
import os
import re
import ssl
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import duckdb
import httpx
import psycopg

import normalize as n
import site_checks
import site_signals as s

OUTPUT = Path("data/staging/site_checks.parquet")
CONCURRENCY = 100
RETRY_CONCURRENCY = 20
RETRY_REASONS = {"timeout", "connection"}
# Χωρίς όριο αναμονής για ελεύθερη σύνδεση: τον ρυθμό τον ορίζει το semaphore.
TIMEOUT = httpx.Timeout(10.0, connect=8.0, pool=None)
MAX_BYTES = 1_500_000
# Κάθε site ξαναελέγχεται αφού περάσουν τόσες μέρες.
RECHECK_DAYS = 30
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 FindMyLead/0.1"
)
_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([\w-]+)""", re.I)

COLUMNS = [
    "website", "status", "reason", "http_status", "final_url", "emails", "socials",
    "social_platforms", "technologies", "eshop", "checked_at",
]


@dataclass
class Check:
    website: str
    status: str = "inactive"
    reason: str | None = None
    http_status: int | None = None
    final_url: str | None = None
    emails: list[str] = field(default_factory=list)
    socials: list[str] = field(default_factory=list)
    social_platforms: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    eshop: bool | None = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def decode(body: bytes, response: httpx.Response) -> str:
    charset = response.charset_encoding
    if not charset:
        match = _META_CHARSET.search(body[:4096])
        charset = match.group(1).decode() if match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


async def fetch(client: httpx.AsyncClient, url: str) -> tuple[httpx.Response, str]:
    async with client.stream("GET", url) as response:
        body = b""
        async for chunk in response.aiter_bytes():
            body += chunk
            if len(body) >= MAX_BYTES:
                break
        return response, decode(body, response)


async def fetch_with_fallback(clients: dict[str, httpx.AsyncClient], website: str):
    """Δοκιμάζει https με έλεγχο πιστοποιητικού, μετά χωρίς, και τέλος http."""
    host_url = website.removeprefix("https://")
    attempts = [
        ("strict", f"https://{host_url}"),
        ("lenient", f"https://{host_url}"),
        ("lenient", f"http://{host_url}"),
    ]
    error: Exception | None = None
    for client_key, url in attempts:
        try:
            return await fetch(clients[client_key], url), None
        except (ssl.SSLError, httpx.ConnectError) as e:
            error = e
            # Το DNS δεν θα απαντήσει διαφορετικά με άλλο πρωτόκολλο.
            if "nodename nor servname" in str(e) or "Name or service not known" in str(e):
                break
        except httpx.HTTPError as e:
            error = e
            break
    return None, error


def classify_error(error: Exception | None) -> str:
    text = f"{type(error).__name__} {error}".lower()
    if "name or service not known" in text or "nodename nor servname" in text or "no address" in text:
        return "dns"
    if "timeout" in text:
        return "timeout"
    if "ssl" in text or "certificate" in text:
        return "ssl"
    if "redirect" in text:
        return "redirects"
    return "connection"


async def check_site(clients: dict[str, httpx.AsyncClient], website: str) -> Check:
    result = Check(website=website)
    fetched, error = await fetch_with_fallback(clients, website)
    if fetched is None:
        result.reason = classify_error(error)
        return result

    response, html = fetched
    final_url = str(response.url)
    final_host = (response.url.host or "").removeprefix("www.")
    result.http_status = response.status_code
    result.final_url = final_url

    if response.status_code in (401, 403, 429, 503) and "cloudflare" in response.headers.get("server", "").lower():
        result.status, result.reason = "active", "blocked"
        return result
    if response.status_code >= 400 and response.status_code not in (401, 403, 429):
        result.reason = f"http_{response.status_code}"
        return result
    if n.website_kind(final_url) in ("social", "platform"):
        result.reason = "redirect_platform"
        return result
    if s.is_placeholder(html, final_host):
        result.reason = "placeholder"
        return result

    result.status = "active"
    if response.status_code in (401, 403, 429):
        result.reason = "blocked"
        return result

    original_site = n.site_key(website)
    if original_site and n.site_key(final_url) != original_site:
        result.reason = "redirect_domain"

    cookies = [c.lower() for c in response.cookies.keys()]
    links = s.extract_links(html, final_url)
    emails = s.extract_emails(html)
    socials = s.extract_socials(links)

    if not emails:
        contact = s.find_contact_page(links, final_host)
        if contact and contact.rstrip("/") != final_url.rstrip("/"):
            try:
                contact_response, contact_html = await fetch(clients["lenient"], contact)
                if contact_response.status_code < 400:
                    emails = s.extract_emails(contact_html)
                    socials = sorted(set(socials) | set(s.extract_socials(s.extract_links(contact_html, contact))))
            except httpx.HTTPError:
                pass

    result.emails = emails
    result.socials = socials
    result.social_platforms = sorted({p for p in map(n.social_platform, socials) if p})
    result.technologies = s.detect_technologies(html, dict(response.headers), cookies)
    result.eshop = s.detect_eshop(html, result.technologies)
    return result


async def crawl(websites: list[str], concurrency: int = CONCURRENCY) -> list[Check]:
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=0)
    common = dict(
        timeout=TIMEOUT,
        follow_redirects=True,
        max_redirects=6,
        limits=limits,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "el,en;q=0.8"},
    )
    semaphore = asyncio.Semaphore(concurrency)
    results: list[Check] = []
    started = time.time()

    async with (
        httpx.AsyncClient(verify=True, **common) as strict,
        httpx.AsyncClient(verify=False, **common) as lenient,
    ):
        clients = {"strict": strict, "lenient": lenient}

        async def worker(website: str) -> None:
            async with semaphore:
                try:
                    # Όριο ανά site, ώστε ένα αργό site να μην κρατάει θέση για πάντα.
                    results.append(await asyncio.wait_for(check_site(clients, website), timeout=45))
                except Exception as e:  # noqa: BLE001
                    results.append(Check(website=website, reason=classify_error(e)))
                done = len(results)
                if done % 500 == 0 or done == len(websites):
                    rate = done / max(time.time() - started, 1)
                    print(f"  {done:,}/{len(websites):,} ({rate:.0f}/s)", flush=True)

        await asyncio.gather(*(worker(w) for w in websites))

        # Πολλά timeouts οφείλονται στον φόρτο του πρώτου γύρου· ξαναδοκιμάζουμε
        # αυτά τα sites με λιγότερα ταυτόχρονα αιτήματα.
        retry = [r.website for r in results if r.reason in RETRY_REASONS]
        if retry:
            print(f"  Δεύτερη προσπάθεια για {len(retry):,} sites", flush=True)
            semaphore = asyncio.Semaphore(RETRY_CONCURRENCY)
            retried: list[Check] = []

            async def retry_worker(website: str) -> None:
                async with semaphore:
                    try:
                        retried.append(await asyncio.wait_for(check_site(clients, website), timeout=60))
                    except Exception as e:  # noqa: BLE001
                        retried.append(Check(website=website, reason=classify_error(e)))

            await asyncio.gather(*(retry_worker(w) for w in retry))
            by_site = {r.website: r for r in retried}
            results = [by_site.get(r.website, r) for r in results]
    return results


def websites_to_check(conn: psycopg.Connection, sample: int | None, shard: tuple[int, int]) -> list[str]:
    conn.execute(site_checks.CREATE)
    index, count = shard
    if sample:
        rows = conn.execute(
            "SELECT website FROM (SELECT DISTINCT website FROM businesses WHERE website IS NOT NULL) w "
            "ORDER BY md5(website) LIMIT %s",
            [sample],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT DISTINCT b.website FROM businesses b
            LEFT JOIN site_checks c USING (website)
            WHERE b.website IS NOT NULL
              AND (c.checked_at IS NULL OR c.checked_at < now() - make_interval(days => %s))
            """,
            [RECHECK_DAYS],
        ).fetchall()
    # Κάθε job του workflow παίρνει το δικό του κομμάτι των sites.
    return [w for (w,) in rows if int(hashlib.md5(w.encode()).hexdigest(), 16) % count == index]


def save(conn: psycopg.Connection, results: list[Check]) -> None:
    with conn.transaction():
        conn.execute("CREATE TEMP TABLE site_checks_new (LIKE site_checks) ON COMMIT DROP")
        with conn.cursor().copy(f"COPY site_checks_new ({', '.join(COLUMNS)}) FROM STDIN") as copy:
            for r in results:
                row = asdict(r)
                copy.write_row([row[c] for c in COLUMNS])
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS if c != "website")
        conn.execute(f"""
            INSERT INTO site_checks SELECT * FROM site_checks_new
            ON CONFLICT (website) DO UPDATE SET {updates}
        """)


def write_parquet(results: list[Check]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    rows = [asdict(r) for r in results]
    con.execute(
        """
        CREATE TABLE checks (
            website VARCHAR, status VARCHAR, reason VARCHAR, http_status INTEGER, final_url VARCHAR,
            emails VARCHAR[], socials VARCHAR[], social_platforms VARCHAR[], technologies VARCHAR[],
            eshop BOOLEAN, checked_at TIMESTAMPTZ
        )
        """
    )
    con.executemany(
        f"INSERT INTO checks VALUES ({', '.join('?' for _ in COLUMNS)})",
        [[row[c] for c in COLUMNS] for row in rows],
    )
    con.execute(f"COPY checks TO '{OUTPUT}' (FORMAT parquet)")


def summarize(results: list[Check]) -> None:
    total = len(results)
    con = duckdb.connect()
    con.sql(f"CREATE VIEW r AS SELECT * FROM '{OUTPUT}'")
    by = lambda expr: con.sql(f"SELECT {expr} AS k, count(*) n FROM r GROUP BY 1 ORDER BY 2 DESC").fetchall()  # noqa: E731
    print(f"\n{total:,} sites")
    print("Κατάσταση:", by("status"))
    print("Λόγος:", by("coalesce(reason, '-')"))
    print("Με email:", con.sql("SELECT count(*) FROM r WHERE len(emails) > 0").fetchall()[0][0])
    print("Με social:", con.sql("SELECT count(*) FROM r WHERE len(socials) > 0").fetchall()[0][0])
    print("E-shop:", con.sql("SELECT count(*) FROM r WHERE eshop").fetchall()[0][0])
    print("Τεχνολογίες:", con.sql("SELECT unnest(technologies) t, count(*) FROM r GROUP BY 1 ORDER BY 2 DESC").fetchall())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, help="έλεγχος σταθερού δείγματος N sites")
    parser.add_argument("--no-save", action="store_true", help="να μη γραφτούν στη βάση")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY)
    parser.add_argument("--shard", default="0/1", help="κομμάτι i/N για παράλληλα jobs (π.χ. 2/4)")
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Λείπει το DATABASE_URL")

    with psycopg.connect(url, autocommit=True) as conn:
        index, count = map(int, args.shard.split("/"))
        websites = websites_to_check(conn, args.sample, (index, count))
    print(f"{len(websites):,} sites για έλεγχο")

    started = time.time()
    results = asyncio.run(crawl(websites, args.concurrency))
    print(f"Έλεγχος σε {time.time() - started:.0f}s")

    if not results:
        return
    write_parquet(results)
    summarize(results)
    if not args.no_save:
        with psycopg.connect(url, autocommit=True) as conn:
            save(conn, results)
            updated = site_checks.apply(conn)
        print(f"Αποθηκεύτηκαν στον πίνακα site_checks, {updated:,} επιχειρήσεις ενημερώθηκαν")


if __name__ == "__main__":
    main()
