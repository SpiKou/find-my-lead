import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))

from normalize import (  # noqa: E402
    is_free_email,
    is_junk_name,
    name_key,
    normalize_email,
    normalize_phone,
    normalize_website,
    phone_type,
    site_key,
    social_platform,
    website_kind,
)


def test_phone_local_and_e164():
    assert normalize_phone("2695 025380") == "+302695025380"
    assert normalize_phone("6907261667") == "+306907261667"
    assert normalize_phone("+30 697 227 7879") == "+306972277879"
    assert normalize_phone("12345") is None
    assert normalize_phone(None) is None


def test_phone_type():
    assert phone_type("+306907261667") == "mobile"
    assert phone_type("+302101234567") == "landline"
    assert phone_type("+4930123456") == "other"


def test_website_kind():
    assert website_kind("https://www.instagram.com/foo") == "social"
    assert website_kind("linktr.ee/foo") == "social"
    assert website_kind("https://www.booking.com/hotel/gr/x.html") == "platform"
    assert website_kind("https://maps.app.goo.gl/abc") == "platform"
    assert website_kind("https://www.elanthipack.gr/") == "own"
    assert website_kind("") is None


def test_site_key():
    assert site_key("https://www.shop.example.com.gr/products") == "example.com.gr"
    assert site_key("alpha.gr/el/branches") == "alpha.gr"
    assert site_key("https://sites.google.com/view/mysite/home") == "sites.google.com/mysite"


def test_normalize_website():
    assert normalize_website("http://www.example.gr/") == "https://example.gr"
    assert normalize_website("example.gr/about/?utm=1") == "https://example.gr/about"


def test_email():
    assert normalize_email(" Info@Example.GR ") == "info@example.gr"
    assert normalize_email("www.pliatsikomilos@gmail.com") == "pliatsikomilos@gmail.com"
    assert normalize_email("not-an-email") is None
    assert is_free_email("someone@gmail.com") is True
    assert is_free_email("info@example.gr") is False


def test_social_platform():
    assert social_platform("https://www.facebook.com/214027455292000") == "facebook"
    assert social_platform("https://twitter.com/foo") == "x"
    assert social_platform("+30 697 227 7879") is None
    assert social_platform("diesel") is None


def test_name_key_and_junk():
    assert name_key("Καφέ Ωραίο!") == name_key("καφε ωραιο")
    assert is_junk_name("043457189") is True
    assert is_junk_name("€$cobar") is False
    assert is_junk_name("00") is True
    assert is_junk_name("1 Euro Cafe") is False
