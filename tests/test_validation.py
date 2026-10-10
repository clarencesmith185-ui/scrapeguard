import pytest

from scrapeguard.validation import parse_value


@pytest.mark.parametrize(
    "raw, kind, expected",
    [
        ("  Hello\n World ", "text", "Hello World"),
        ("+42", "integer", 42),
        ("-3", "integer", -3),
        ("1.2e2", "number", 120.0),
        (".25", "number", 0.25),
        ("/products/one", "url", "https://example.com/products/one"),
        ("https://other.example/a", "url", "https://other.example/a"),
    ],
)
def test_values(raw, kind, expected):
    assert parse_value(raw, kind, "https://example.com/base/") == expected


@pytest.mark.parametrize(
    "raw, kind",
    [
        (None, "text"),
        ("", "text"),
        ("\n", "text"),
        ("1.0", "integer"),
        ("1,000", "integer"),
        ("NaN", "number"),
        ("inf", "number"),
        ("1e999", "number"),
        ("RM 5.20", "number"),
        ("javascript:alert(1)", "url"),
        ("https://example.com/a b", "url"),
        ("http:///missing", "url"),
    ],
)
def test_invalid_values(raw, kind):
    with pytest.raises(ValueError):
        parse_value(raw, kind, "https://example.com/base/")
