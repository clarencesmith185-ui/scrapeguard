from dataclasses import replace

import pytest

from scrapeguard import FieldConfig, Snapshot, TargetConfig, inspect_page


def target(*fields):
    return TargetConfig("quote", "https://example.com", tuple(fields))


def capture(page, fixture, field):
    page.goto(fixture.as_uri())
    result = inspect_page(page, target(field))
    assert result.ok
    observed = result.fields[0]
    return {field.name: Snapshot(observed.value, observed.context)}


def test_baseline_and_unchanged_real_html(page, fixtures):
    fields = (
        FieldConfig("price", ".price", "number"),
        FieldConfig("volume", ".volume", "integer"),
        FieldConfig("name", "h1"),
        FieldConfig("url", ".link", "url", "href"),
    )
    page.goto((fixtures / "original.html").as_uri())
    first = inspect_page(page, target(*fields))
    baseline = {f.name: Snapshot(f.value, f.context) for f in first.fields}
    checked = inspect_page(page, target(*fields), baseline)
    assert checked.ok
    assert [f.value for f in checked.fields] == [
        5.2,
        42,
        "Example Stock",
        "https://example.com/stocks/ABC",
    ]
    assert baseline["price"].context["parents"][0]["attributes"]["id"] == "quote"
    assert 'class="price"' in baseline["price"].context["html"]


def test_missing_selector_suggests_without_changing_page(page, fixtures):
    field = FieldConfig("price", ".price", "number")
    baseline = capture(page, fixtures / "original.html", field)
    page.goto((fixtures / "renamed.html").as_uri())
    html = page.content()
    finding = inspect_page(page, target(field), baseline).fields[0]
    assert finding.status == "missing"
    assert finding.match_count == 0
    assert finding.suggestions[0].selector == "[data-testid=current-price]"
    assert page.locator(finding.suggestions[0].selector).count() == 1
    assert page.content() == html


def test_ambiguous_selector_is_not_silently_first_matched(page, fixtures):
    field = FieldConfig("price", ".price", "number")
    baseline = capture(page, fixtures / "original.html", field)
    page.goto((fixtures / "ambiguous.html").as_uri())
    finding = inspect_page(page, target(field), baseline).fields[0]
    assert finding.status == "ambiguous"
    assert finding.match_count == 2
    assert finding.value is None
    assert finding.suggestions[0].selector == "[data-testid=price]"


@pytest.mark.parametrize(
    "html",
    [
        '<section id="quote"><div id="a">5.20</div><div id="b">5.20</div></section>',
        '<section id="unrelated"><div id="a">5.20</div></section>',
        '<section id="quote"><div id="a">9.00</div></section>',
        '<section id="quote"><div id="a">not a number</div></section>',
    ],
)
def test_uncertain_suggestions_abstain(page, fixtures, html):
    field = FieldConfig("price", ".price", "number")
    baseline = capture(page, fixtures / "original.html", field)
    page.set_content(html)
    result = inspect_page(page, target(field), baseline).fields[0]
    assert result.status == "missing"
    assert result.suggestions == []


def test_no_ancestor_anchor_abstains(page):
    field = FieldConfig("price", ".price", "number")
    page.set_content('<span class="price">5.2</span>')
    result = inspect_page(page, target(field)).fields[0]
    baseline = {"price": Snapshot(result.value, result.context)}
    page.set_content('<div id="new-price">5.2</div>')
    assert not inspect_page(page, target(field), baseline).fields[0].suggestions


def test_suggestion_escapes_css_attribute_values(page, fixtures):
    field = FieldConfig("price", ".price", "number")
    baseline = capture(page, fixtures / "original.html", field)
    page.set_content('<section id="quote"><div data-testid=\'new"price\'>5.2</div></section>')
    finding = inspect_page(page, target(field), baseline).fields[0]
    assert finding.suggestions
    assert page.locator(finding.suggestions[0].selector).count() == 1


def test_scan_limit_abstains(page, fixtures):
    field = FieldConfig("price", ".price", "number")
    baseline = capture(page, fixtures / "original.html", field)
    page.set_content(
        '<section id="quote"><div id="new">5.2</div></section>'
        + "".join(f'<b id="n{i}">other</b>' for i in range(1000))
    )
    assert not inspect_page(page, target(field), baseline).fields[0].suggestions


def test_changed_data_and_opt_out(page, fixtures):
    field = FieldConfig("price", ".price", "number")
    baseline = capture(page, fixtures / "original.html", field)
    page.locator(".price").evaluate("el => el.textContent = '6.50'")
    finding = inspect_page(page, target(field), baseline).fields[0]
    assert (finding.status, finding.value, finding.previous_value) == ("changed", 6.5, 5.2)
    assert inspect_page(page, target(replace(field, track_changes=False)), baseline).ok
    page.locator(".price").evaluate("el => el.textContent = 'invalid'")
    assert not inspect_page(page, target(replace(field, track_changes=False)), baseline).ok


def test_text_whitespace_and_numeric_format_are_normalized(page):
    fields = (FieldConfig("name", "h1"), FieldConfig("price", "span", "number"))
    page.set_content("<h1>Example Stock</h1><span>5.20</span>")
    first = inspect_page(page, target(*fields))
    baseline = {f.name: Snapshot(f.value, f.context) for f in first.fields}
    page.set_content("<h1> Example\n  Stock </h1><span>5.2000</span>")
    assert inspect_page(page, target(*fields), baseline).ok


def test_invalid_selector_does_not_prevent_other_fields(page):
    page.set_content("<h1>Stock</h1>")
    result = inspect_page(page, target(FieldConfig("bad", "["), FieldConfig("good", "h1")))
    assert [f.status for f in result.fields] == ["invalid_selector", "ok"]


@pytest.mark.parametrize(
    "field, html",
    [
        (FieldConfig("price", "span", "number"), "<span>RM 5.20</span>"),
        (FieldConfig("stock", "span", "integer"), "<span>1.5</span>"),
        (FieldConfig("name", "span"), "<span> </span>"),
        (FieldConfig("link", "a", "url", "href"), "<a>No href</a>"),
    ],
)
def test_invalid_extracted_data(page, field, html):
    page.set_content(html)
    assert inspect_page(page, target(field)).fields[0].status == "invalid_data"


def test_context_is_bounded(page):
    page.set_content('<section id="quote"><span>' + "a" * 5000 + "</span></section>")
    result = inspect_page(page, target(FieldConfig("value", "span"))).fields[0]
    assert len(result.value) == 5000
    assert len(result.context["html"]) == 1000
    assert len(result.context["text"]) == 512
    assert len(result.context["parents"][0]["text"]) == 300


def test_partial_library_baseline_is_reported(page):
    page.set_content("<h1>Stock</h1>")
    result = inspect_page(page, target(FieldConfig("name", "h1")), {})
    assert result.fields[0].status == "baseline_missing"
