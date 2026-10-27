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

_TECH_PATTERNS = {
    tech: {kind: [re.compile(p, re.I) for p in patterns] for kind, patterns in rules.items()}
    for tech, rules in TECH_RULES.items()
}

ESHOP_PLATFORMS = {"WooCommerce", "Shopify", "OpenCart", "PrestaShop", "Magento"}
_ESHOP_MARKERS = re.compile(
    r"add[-_ ]to[-_ ]cart|προσθήκη στο καλάθι|"
    r"\"@type\"\s*:\s*\"product\"|og:type\"\s+content=\"product|"
    r"wix-ecommerce|ecwid|cs-cart|shopflix",
    re.I,
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
    re.I,
)

_HREF = re.compile(r"""href\s*=\s*["']([^"'#\s]+)""", re.I)
_MAILTO = re.compile(r"""mailto:([^"'?\s>]+)""", re.I)
_EMAIL_TEXT = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.[a-z]{2,}", re.I)
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
    header_lines = [f"{k.lower()}: {v}" for k, v in headers.items()]
    found = set()
    for tech, kinds in _TECH_PATTERNS.items():
        if any(p.search(html) for p in kinds.get("html", [])) or any(
            p.search(line) for p in kinds.get("headers", []) for line in header_lines
        ) or any(p.search(c) for p in kinds.get("cookies", []) for c in cookies):
            found.add(tech)
    for tech, implied in TECH_IMPLIES.items():
        if tech in found:
            found.add(implied)
    return sorted(found)


def detect_eshop(html: str, technologies: list[str]) -> bool:
    return bool(ESHOP_PLATFORMS.intersection(technologies)) or bool(_ESHOP_MARKERS.search(html))


def is_placeholder(html: str, final_host: str) -> bool:
    domain = n._tld(final_host).top_domain_under_public_suffix
    return domain in PARKED_HOSTS or bool(_PLACEHOLDER.search(html[:20000]))


def extract_emails(html: str) -> list[str]:
    raw = _MAILTO.findall(html) + _EMAIL_TEXT.findall(html)
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
