import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

import site_signals as s  # noqa: E402


def test_technologies():
    wp = '<link rel="stylesheet" href="/wp-content/themes/astra/style.css">'
    assert s.detect_technologies(wp, {}, []) == ["WordPress"]
    woo = wp + '<body class="woocommerce-no-js"><script src="/wp-content/plugins/woocommerce/x.js">'
    assert s.detect_technologies(woo, {}, []) == ["WooCommerce", "WordPress"]
    # Θέμα με CSS για WooCommerce, χωρίς το plugin.
    assert s.detect_technologies(wp + '<link href="/theme/woocommerce.css">', {}, []) == ["WordPress"]
    assert s.detect_technologies('<script src="/_next/static/chunks/main.js">', {}, []) == ["Next.js", "React"]
    assert s.detect_technologies("", {"X-Wix-Request-Id": "1"}, []) == ["Wix"]
    assert s.detect_technologies("", {}, ["ocsessid"]) == ["OpenCart"]
    assert s.detect_technologies("<html><body>Hello</body></html>", {}, []) == []


def test_eshop():
    assert s.detect_eshop("", ["Shopify"])
    assert s.detect_eshop('<button class="add_to_cart_button">', [])
    assert s.detect_eshop("<button>Προσθήκη στο καλάθι</button>", [])
    assert not s.detect_eshop("<p>Λογιστικό γραφείο</p>", ["WordPress"])


def test_placeholder():
    assert s.is_placeholder("<h1>This domain is for sale!</h1>", "example.gr")
    assert s.is_placeholder("<title>Apache2 Ubuntu Default Page</title>", "example.gr")
    assert s.is_placeholder("<p>Hi</p>", "sedoparking.com")
    assert not s.is_placeholder("<p>Καλώς ήρθατε στο κατάστημά μας</p>", "example.gr")


def test_emails():
    html = (
        '<a href="mailto:Info@Example-Shop.gr?subject=Hi">Mail</a> sales@example-shop.gr '
        '<img src="logo@2x.png"> email@paradeigma.gr donate@opencart.com x@sentry.io'
    )
    assert s.extract_emails(html) == ["info@example-shop.gr", "sales@example-shop.gr"]


def test_socials():
    links = [
        "https://www.facebook.com/myshop/",
        "https://facebook.com/sharer/sharer.php?u=x",
        "https://www.facebook.com/profile.php?id=1234567",
        "https://www.facebook.com/profile.php",
        "https://instagram.com/myshop",
        "https://instagram.com/p/AbC123/",
        "https://pinterest.com/pin/create/button/?url=x",
        "https://www.facebook.com/Plesk",
        "https://example.gr/contact",
    ]
    assert s.extract_socials(links) == [
        "https://facebook.com/myshop",
        "https://facebook.com/profile.php?id=1234567",
        "https://instagram.com/myshop",
    ]


def test_contact_page():
    links = ["https://example.gr/about", "https://www.example.gr/epikoinonia/", "https://other.gr/contact"]
    assert s.find_contact_page(links, "example.gr") == "https://www.example.gr/epikoinonia/"
