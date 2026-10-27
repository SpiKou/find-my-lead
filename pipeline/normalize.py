"""Συναρτήσεις κανονικοποίησης για τηλέφωνα, websites, emails, socials και ονόματα.

Είναι καθαρές συναρτήσεις (χωρίς I/O) ώστε να τεστάρονται εύκολα και να
καλούνται ως UDF από το DuckDB.
"""

import re
import unicodedata
from urllib.parse import urlsplit

import phonenumbers
import tldextract

# Χρησιμοποιούμε το snapshot της Public Suffix List που έρχεται με το πακέτο,
# ώστε να μη γίνεται λήψη από το internet σε κάθε τρέξιμο.
_tld = tldextract.TLDExtract(suffix_list_urls=())

# Domains που δηλώνονται ως "website" αλλά δεν είναι δικό site της επιχείρησης.
SOCIAL_HOSTS = {
    "facebook.com", "fb.com", "fb.me", "instagram.com", "tiktok.com", "youtube.com",
    "youtu.be", "twitter.com", "x.com", "linkedin.com", "pinterest.com",
    "linktr.ee", "linkin.bio", "beacons.ai", "wa.me", "m.me",
}
PLATFORM_HOSTS = {
    "booking.com", "airbnb.gr", "airbnb.com", "e-food.gr", "efood.gr", "wolt.com",
    "box.gr", "tripadvisor.com", "tripadvisor.com.gr", "tripadvisor.gr",
    "google.com", "goo.gl", "g.co", "g.page", "business.site", "vrbo.com",
    "expedia.com", "hotels.com", "doctoranytime.gr", "vrisko.gr", "xo.gr",
    "11880.com", "skroutz.gr", "eventbrite.com", "ubereats.com", "foody.gr",
    "wikipedia.org",
}
# Δωρεάν hosting όπου κάθε υποφάκελος είναι διαφορετικό site.
SHARED_PATH_HOSTS = {"sites.google.com", "blogs.sch.gr"}
# Δωρεάν hosting όπου κάθε subdomain είναι διαφορετικό site (xyz.blogspot.gr).
SHARED_SUBDOMAIN_DOMAINS = {
    "blogspot.com", "blogspot.gr", "wixsite.com", "wordpress.com", "webnode.gr",
    "webnode.com", "weebly.com", "sch.gr", "car.gr", "4ty.gr", "business.site",
    "squarespace.com", "jimdofree.com", "jimdosite.com", "site123.me", "mozello.com",
    "github.io", "netlify.app", "vercel.app",
}

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.gr", "yahoo.gr",
    "yahoo.com", "otenet.gr", "outlook.com", "outlook.com.gr", "windowslive.com",
    "icloud.com", "live.com", "live.gr", "msn.com", "me.com", "protonmail.com",
    "proton.me", "aol.com", "mail.com", "gmx.com", "gmx.net", "yandex.com",
    "freemail.gr", "in.gr", "forthnet.gr", "hol.gr", "windtools.gr",
}

SOCIAL_PLATFORMS = {
    "facebook.com": "facebook", "fb.com": "facebook", "instagram.com": "instagram",
    "twitter.com": "x", "x.com": "x", "linkedin.com": "linkedin",
    "youtube.com": "youtube", "tiktok.com": "tiktok", "pinterest.com": "pinterest",
}

_EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")


def normalize_phone(raw: str | None) -> str | None:
    """Επιστρέφει τηλέφωνο σε μορφή E.164 (+30...) ή None αν δεν είναι έγκυρο."""
    if not raw:
        return None
    try:
        number = phonenumbers.parse(raw, "GR")
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def phone_type(e164: str | None) -> str | None:
    """'mobile', 'landline' ή 'other' για ελληνικά νούμερα."""
    if not e164:
        return None
    if e164.startswith("+3069"):
        return "mobile"
    if e164.startswith("+302"):
        return "landline"
    return "other"


def _host_and_path(raw: str) -> tuple[str, str] | None:
    url = raw.strip()
    if not url:
        return None
    if "://" not in url:
        url = "http://" + url
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    host = (parts.hostname or "").lower().removeprefix("www.")
    if not host or "." not in host:
        return None
    return host, parts.path


def website_kind(raw: str | None) -> str | None:
    """'own' για δικό site, 'social' ή 'platform' για τρίτες πλατφόρμες."""
    if not raw:
        return None
    hp = _host_and_path(raw)
    if not hp:
        return None
    domain = _tld(hp[0]).top_domain_under_public_suffix
    if domain in SOCIAL_HOSTS or hp[0] in SOCIAL_HOSTS:
        return "social"
    if domain in PLATFORM_HOSTS or hp[0] in PLATFORM_HOSTS:
        return "platform"
    return "own"


def site_key(raw: str | None) -> str | None:
    """Κλειδί που ταυτίζει το ίδιο site: το registered domain (π.χ. example.com.gr).

    Για κοινόχρηστο hosting κρατάει ολόκληρο το subdomain (xyz.blogspot.gr) ή
    τον πρώτο υποφάκελο (sites.google.com/view/xyz).
    """
    if not raw:
        return None
    hp = _host_and_path(raw)
    if not hp:
        return None
    host, path = hp
    if host in SHARED_PATH_HOSTS:
        first = next((p for p in path.split("/") if p and p != "view"), "")
        return f"{host}/{first.lower()}" if first else host
    domain = _tld(host).top_domain_under_public_suffix
    if domain in SHARED_SUBDOMAIN_DOMAINS and host != domain:
        return host
    return domain or None


def normalize_website(raw: str | None) -> str | None:
    """Καθαρό URL: https, χωρίς www και χωρίς query/fragment."""
    if not raw:
        return None
    hp = _host_and_path(raw)
    if not hp:
        return None
    host, path = hp
    path = path.rstrip("/")
    return f"https://{host}{path}"


def normalize_email(raw: str | None) -> str | None:
    if not raw:
        return None
    email = raw.strip().lower().removeprefix("mailto:").removeprefix("www.")
    return email if _EMAIL_RE.match(email) else None


def is_free_email(email: str | None) -> bool | None:
    if not email:
        return None
    return email.split("@", 1)[1] in FREE_EMAIL_DOMAINS


def social_platform(raw: str | None) -> str | None:
    """Η πλατφόρμα ενός social URL, ή None αν δεν είναι έγκυρο URL γνωστής πλατφόρμας."""
    if not raw:
        return None
    hp = _host_and_path(raw)
    if not hp:
        return None
    domain = _tld(hp[0]).top_domain_under_public_suffix
    return SOCIAL_PLATFORMS.get(domain)


def name_key(name: str | None) -> str | None:
    """Κλειδί ονόματος για σύγκριση: πεζά, χωρίς τόνους, μόνο γράμματα και ψηφία."""
    if not name:
        return None
    decomposed = unicodedata.normalize("NFKD", name.lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    key = re.sub(r"[^\w]+", "", stripped).replace("_", "")
    return key or None


def name_search(name: str | None) -> str | None:
    """Όνομα για αναζήτηση με κανόνες: πεζά, χωρίς τόνους, με κενά."""
    if not name:
        return None
    decomposed = unicodedata.normalize("NFKD", name.lower())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip() or None


def is_junk_name(name: str | None) -> bool:
    """Ονόματα που δεν είναι επιχείρηση: κενά, μόνο αριθμοί ή τηλέφωνα, μόνο σύμβολα."""
    if not name or not name.strip():
        return True
    letters = sum(c.isalpha() for c in name)
    return letters < 2
