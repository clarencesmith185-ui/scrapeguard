"""Inspect an existing synchronous Playwright Page without navigating or modifying it."""

from __future__ import annotations

from collections.abc import Mapping

from playwright.sync_api import Error, Page

from .models import FieldConfig, FieldResult, Snapshot, Suggestion, TargetConfig, TargetResult
from .validation import parse_value

# Read counts, extraction, and bounded context in one browser evaluation per field.
# Native CSS is deliberately the only selector language supported by v0.1.
_DOM_HELPERS = r"""
const allowed = ['id', 'class', 'data-testid', 'data-test', 'name', 'role',
                 'aria-label', 'itemprop', 'title'];
const attrs = el => Object.fromEntries(allowed.filter(a => el.hasAttribute(a))
    .map(a => [a, el.getAttribute(a).slice(0, 512)]));
const norm = s => s.replace(/\s+/g, ' ').trim();
const context = el => {
    const parents = [];
    let parent = el.parentElement;
    for (let i = 0; parent && i < 3; i++, parent = parent.parentElement) {
        if (['BODY', 'HTML'].includes(parent.tagName)) break;
        parents.push({tag: parent.tagName.toLowerCase(), attributes: attrs(parent),
            text: norm(parent.textContent || '').slice(0, 300)});
    }
    return {tag: el.tagName.toLowerCase(), attributes: attrs(el),
        text: norm(el.textContent || '').slice(0, 512),
        html: el.outerHTML.slice(0, 1000), parents};
};
const raw = el => arg.attribute ? el.getAttribute(arg.attribute) : el.textContent;
"""

_INSPECT = (
    "(arg) => {"
    + _DOM_HELPERS
    + r"""
    let matches;
    try { matches = document.querySelectorAll(arg.selector); }
    catch (e) { return {selector_error: e.message}; }
    if (matches.length !== 1) return {count: matches.length};
    const el = matches[0];
    return {count: 1, raw: raw(el), base_url: el.baseURI, context: context(el)};
}
"""
)

_CANDIDATES = (
    "(arg) => {"
    + _DOM_HELPERS
    + r"""
    const nodes = document.querySelectorAll(
        '[data-testid], [data-test], [id], [name], [itemprop], [class]');
    // Never make a suggestion based on an incomplete scan.
    if (nodes.length > 1000) return [];
    return Array.from(nodes).map(el => {
        const selectors = [];
        for (const key of ['data-testid', 'data-test', 'id', 'name', 'itemprop']) {
            const value = el.getAttribute(key);
            if (value) selectors.push(`[${key}=${CSS.escape(value)}]`);
        }
        for (const token of Array.from(el.classList).slice(0, 3)) {
            selectors.push(`${el.tagName.toLowerCase()}.${CSS.escape(token)}`);
        }
        return {raw: raw(el), base_url: el.baseURI, context: context(el),
            selectors: selectors.filter(s => document.querySelectorAll(s).length === 1)};
    }).filter(c => c.selectors.length);
}
"""
)


def _anchors(context: dict) -> set[tuple[str, str]]:
    return {
        (key, value)
        for parent in context.get("parents", [])
        for key, value in parent.get("attributes", {}).items()
        if key in ("id", "data-testid", "data-test") and value
    }


def _suggest(page: Page, field: FieldConfig, previous: Snapshot) -> list[Suggestion]:
    anchors = _anchors(previous.context)
    if not anchors:
        return []
    candidates = page.evaluate(_CANDIDATES, {"attribute": field.attribute})
    eligible = []
    for candidate in candidates:
        if not anchors.intersection(_anchors(candidate["context"])):
            continue
        try:
            value = parse_value(candidate["raw"], field.type, candidate["base_url"])
        except ValueError:
            continue
        if value == previous.value:
            eligible.append(candidate)
    # Shared values among multiple elements do not justify choosing one arbitrarily.
    if len(eligible) != 1:
        return []
    return [
        Suggestion(
            selector, "Unique match with the same validated value and ancestor id/test marker"
        )
        for selector in eligible[0]["selectors"][:3]
    ]


def inspect_page(
    page: Page,
    target: TargetConfig,
    baseline: Mapping[str, Snapshot] | None = None,
) -> TargetResult:
    """Inspect a loaded Page. No navigation, waits, patches, or baseline writes.

    Use this directly inside an existing scraper after its own login/navigation/waits.
    Pass no baseline for initial capture, or the target's saved snapshots for comparison.
    """
    result = TargetResult(target.name, page.url)
    for field in target.fields:
        previous = baseline.get(field.name) if baseline is not None else None
        try:
            observation = page.evaluate(
                _INSPECT, {"selector": field.selector, "attribute": field.attribute}
            )
            if "selector_error" in observation:
                entry = FieldResult(
                    field.name,
                    field.selector,
                    "invalid_selector",
                    f"Invalid CSS selector: {observation['selector_error']}",
                )
            elif observation["count"] != 1:
                count = observation["count"]
                entry = FieldResult(
                    field.name,
                    field.selector,
                    "missing" if count == 0 else "ambiguous",
                    "Selector matched no elements; inspect the page or review suggestions."
                    if count == 0
                    else f"Selector matched {count} elements; narrow it to one.",
                    match_count=count,
                    previous_value=previous.value if previous else None,
                )
                if previous:
                    entry.suggestions = _suggest(page, field, previous)
            else:
                entry = FieldResult(
                    field.name,
                    field.selector,
                    "ok",
                    "Exactly one match; output type is valid.",
                    match_count=1,
                    context=observation["context"],
                    previous_value=previous.value if previous else None,
                )
                try:
                    entry.value = parse_value(
                        observation["raw"], field.type, observation["base_url"]
                    )
                except ValueError as exc:
                    entry.status, entry.message = "invalid_data", str(exc)
                else:
                    if previous and field.track_changes and entry.value != previous.value:
                        entry.status = "changed"
                        entry.message = (
                            "Value differs from baseline; verify data or refresh baseline."
                        )
            if baseline is not None and previous is None:
                entry.status = "baseline_missing"
                entry.message = "No baseline for this field; create a new baseline."
            result.fields.append(entry)
        except Error as exc:
            result.fields.append(
                FieldResult(
                    field.name, field.selector, "page_error", f"Could not inspect page: {exc}"
                )
            )
    return result
