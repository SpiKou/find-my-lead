"""Ανάλυση της σελίδας ενός site: κατάσταση, emails, socials, τεχνολογίες, e-shop.

Καθαρές συναρτήσεις πάνω σε HTML και headers, ώστε να τεστάρονται χωρίς δίκτυο.
"""

import re
from urllib.parse import urljoin, urlsplit

import normalize as n

# Οι 16 τεχνολογίες του φίλτρου (docs/filters.md). Κάθε κανόνας ψάχνει στο
# HTML, στα headers ή στα ονόματα των cookies.
TECH_RULES: dict[str, dict[str, list[str]]] = {
    "WordPress": {
        "html": [r"/wp-content/", r"/wp-includes/", r'<meta[^>]+generator[^>]+wordpress'],
        "headers": [r"link:.*api\.w\.org"],
    },
    "WooCommerce": {
        # Σκέτο "woocommerce" εμφανίζεται και σε themes χωρίς κατάστημα.
        "html": [
            r"/wp-content/plugins/woocommerce/", r"wc-ajax=", r"woocommerce-no-js",
            r"wc_add_to_cart_params", r"woocommerce_params",
        ],
    },
    "Joomla": {
        "html": [r'<meta[^>]+generator[^>]+joomla', r"/media/jui/", r"/media/system/js/", r"/components/com_"],
    },
    "OpenCart": {
        "html": [r"index\.php\?route=(common|product)/", r"catalog/view/theme/"],
        "cookies": [r"^ocsessid$"],
    },
    "Wix": {
        "html": [r"static\.wixstatic\.com", r"static\.parastorage\.com"],
        "headers": [r"^x-wix-request-id:"],
    },
    "Shopify": {
        "html": [r"cdn\.shopify\.com", r"shopify\.theme"],
        "headers": [r"^x-shopid:", r"^x-shopify-stage:"],
    },
    "Next.js": {
        "html": [r"/_next/static/", r"__NEXT_DATA__"],
        "headers": [r"^x-powered-by:\s*next\.js"],
    },
    "PrestaShop": {
        "html": [r'<meta[^>]+generator[^>]+prestashop', r"var prestashop\s*=", r"/modules/ps_[a-z]+/"],
    },
    "Drupal": {
        "html": [r'<meta[^>]+generator[^>]+drupal', r"/sites/default/files/", r"drupal-settings-json"],
        "headers": [r"^x-drupal-cache:", r"^x-generator:\s*drupal"],
    },
    "Magento": {
        "html": [r"text/x-magento-init", r"mage/cookies", r"/static/version\d+/frontend/", r"/skin/frontend/"],
    },
    "Angular": {
        "html": [r"\sng-version=\"", r"\sng-app[=\s>]"],
    },
    "Squarespace": {
        "html": [r"static1\.squarespace\.com", r"squarespace-cdn\.com"],
    },
    "Webflow": {
        "html": [r"\sdata-wf-page=", r"website-files\.com/", r"webflow\.js"],
    },
    "Nuxt": {
        "html": [r"__NUXT__", r"/_nuxt/"],
    },
    "React": {
        "html": [r"data-reactroot", r"react-dom(\.production)?(\.min)?\.js"],
    },
    "Vue": {
        "html": [r"\sdata-v-[0-9a-f]{8}", r"vue(\.runtime)?(\.global)?(\.prod)?(\.min)?\.js"],
    },
}
# Τεχνολογίες που προϋποθέτουν άλλες (όπως στο Wappalyzer).
TECH_IMPLIES = {"Next.js": "React", "Nuxt": "Vue", "WooCommerce": "WordPress"}


def _literal_prefix(pattern: str) -> str:
    """Το σταθερό κείμενο με το οποίο ξεκινά ένα μοτίβο (π.χ. "/wp-content/")."""
    text = pattern.lower().removeprefix(r"\s").replace(r"\.", ".").replace(r"\?", "?")
    prefix = ""
    for ch in text:
        if ch in "()[]*+{}|\\^$" or (ch == "?" and prefix and not prefix.endswith(".php")):
            break
        prefix += ch
    return prefix


# Για κάθε μοτίβο κρατάμε το σταθερό του πρόθεμα: το regex τρέχει μόνο αν το
# πρόθεμα υπάρχει στη σελίδα, που είναι πολύ πιο φθηνός έλεγχος.
_TECH_PATTERNS = {
    tech: {kind: [(_literal_prefix(p), re.compile(p.lower())) for p in patterns] for kind, patterns in rules.items()}
    for tech, rules in TECH_RULES.items()
}


def _matches(rules: list[tuple[str, re.Pattern]], text: str) -> bool:
    return any((not prefix or prefix in text) and pattern.search(text) for prefix, pattern in rules)

ESHOP_PLATFORMS = {"WooCommerce", "Shopify", "OpenCart", "PrestaShop", "Magento"}
_ESHOP_MARKERS = re.compile(
    r"add[-_ ]to[-_ ]cart|προσθήκη στο καλάθι|"
    r"\"@type\"\s*:\s*\"product\"|og:type\"\s+content=\"product|"
    r"wix-ecommerce|ecwid|cs-cart|shopflix",
)

# Σελίδες «προς πώληση», προεπιλεγμένες σελίδες server, ανεσταλμένοι λογαριασμοί.
PARKED_HOSTS = {
    "sedo.com", "sedoparking.com", "dan.com", "afternic.com", "hugedomains.com",
    "parkingcrew.net", "bodis.com", "above.com", "domainmarket.com", "godaddy.com",
    "namecheap.com", "papaki.com", "top.host", "dnhost.gr", "hostinger.com",
}
_PLACEHOLDER = re.compile(
    r"this domain (name )?(is|may be) for sale|buy this domain|domain is parked|"
    r"parked free|το domain (αυτό )?(πωλείται|είναι προς πώληση)|"
    r"apache2 (ubuntu|debian) default page|welcome to nginx!|<title>\s*index of /|"
    r"account (has been )?suspended|this account has been suspended|"
    r"default web site page|web hosting by plesk|<title>\s*cpanel|"
    r"future home of something quite cool|website is under construction",
)

_HREF = re.compile(r"""href\s*=\s*["']([^"'#\s]+)""", re.I)
_MAILTO = re.compile(r"""mailto:([^"'?\s>]+)""", re.I)
_EMAIL_TEXT = re.compile(r"[a-z0-9._%+\-]{1,64}@[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.[a-z]{2,}")
# Πόσα "@" της σελίδας εξετάζονται το πολύ για emails.
MAX_AT_SIGNS = 500
_EMAIL_JUNK = re.compile(
    r"\.(png|jpe?g|gif|webp|svg|css|js)$|"
    r"@(example|domain|email|sentry|wixpress|sentry-next|paradeigma|mydomain|yourdomain|"
    r"yoursite|company|opencart|wordpress|woocommerce|prestashop|joomla)\.|"
    r"^(name|your|you|user|email|info|test)@(domain|example|email|test)\.",
    re.I,
)
_SOCIAL_JUNK = re.compile(
    r"sharer|/share|/intent/|/dialog/|/plugins/|facebook\.com/tr|/hashtag/|"
    r"/watch\?|/embed/|/p/[A-Za-z0-9_-]+/?$|/reel/|/status/|/events?/|/groups/|"
    r"/policies|/legal|/help|/privacy|/about/?$|/login|/home\.php|/pin/|"
    # Λογαριασμοί κατασκευαστών και πλατφορμών που μπαίνουν σε templates.
    r"\.com/(plesk|wix|wordpress|woocommerce|opencart|prestashop|shopify|elementor|"
    r"godaddy|papaki|hostinger|joomla|drupal|squarespace|webflow|envato|themeforest)/?$",
    re.I,
)
_CONTACT_LINK = re.compile(r"contact|epikoinon|επικοινων|kontakt", re.I)


def detect_technologies(html: str, headers: dict[str, str], cookies: list[str]) -> list[str]:
    lower = html.lower()
    header_lines = [f"{k}: {v}".lower() for k, v in headers.items()]
    found = set()
    for tech, kinds in _TECH_PATTERNS.items():
        if (
            _matches(kinds.get("html", []), lower)
            or any(_matches(kinds.get("headers", []), line) for line in header_lines)
            or any(_matches(kinds.get("cookies", []), c.lower()) for c in cookies)
        ):
            found.add(tech)
    for tech, implied in TECH_IMPLIES.items():
        if tech in found:
            found.add(implied)
    return sorted(found)


def detect_eshop(html: str, technologies: list[str]) -> bool:
    return bool(ESHOP_PLATFORMS.intersection(technologies)) or bool(_ESHOP_MARKERS.search(html.lower()))


def is_placeholder(html: str, final_host: str) -> bool:
    domain = n._tld(final_host).top_domain_under_public_suffix
    return domain in PARKED_HOSTS or bool(_PLACEHOLDER.search(html[:20000].lower()))


def extract_emails(html: str) -> list[str]:
    # Το regex τρέχει μόνο γύρω από κάθε "@" και όχι σε όλη τη σελίδα.
    lower = html.lower()
    raw = _MAILTO.findall(html)
    start = 0
    for _ in range(MAX_AT_SIGNS):
        at = lower.find("@", start)
        if at < 0:
            break
        raw += _EMAIL_TEXT.findall(lower, max(0, at - 64), at + 256)
        start = at + 1
    emails = set()
    for value in raw:
        email = n.normalize_email(value.split("?")[0])
        if email and not _EMAIL_JUNK.search(email):
            emails.add(email)
    return sorted(emails)


def extract_links(html: str, base_url: str) -> list[str]:
    links = []
    for href in _HREF.findall(html):
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        try:
            links.append(urljoin(base_url, href))
        except ValueError:
            continue
    return links


def extract_socials(links: list[str]) -> list[str]:
    socials = {}
    for link in links:
        platform = n.social_platform(link)
        if not platform or _SOCIAL_JUNK.search(link):
            continue
        parts = urlsplit(link)
        path = parts.path.rstrip("/")
        if not path or path.count("/") > 3:
            continue
        url = f"https://{parts.hostname.removeprefix('www.').removeprefix('m.')}{path}"
        # Τα προφίλ Facebook χωρίς όνομα ξεχωρίζουν μόνο από το ?id=.
        if path.endswith("/profile.php"):
            match = re.search(r"(?:^|&)id=(\d+)", parts.query)
            if not match:
                continue
            url += f"?id={match.group(1)}"
        socials.setdefault(url.lower(), url)
    return sorted(socials.values())


def find_contact_page(links: list[str], site_host: str) -> str | None:
    for link in links:
        parts = urlsplit(link)
        host = (parts.hostname or "").removeprefix("www.")
        if host == site_host and _CONTACT_LINK.search(parts.path):
            return link
    return None


def analyze(html: str, headers: dict[str, str], cookies: list[str], final_url: str, final_host: str) -> dict:
    """Όλη η ανάλυση μιας σελίδας μαζί, για να τρέχει σε ξεχωριστή διεργασία."""
    links = extract_links(html, final_url)
    technologies = detect_technologies(html, headers, cookies)
    return {
        "placeholder": is_placeholder(html, final_host),
        "emails": extract_emails(html),
        "socials": extract_socials(links),
        "contact_page": find_contact_page(links, final_host),
        "technologies": technologies,
        "eshop": detect_eshop(html, technologies),
    }


def analyze_contact(html: str, url: str) -> tuple[list[str], list[str]]:
    return extract_emails(html), extract_socials(extract_links(html, url))
