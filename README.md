# ScrapeGuard

**Know when your Playwright scraper stops extracting what you expect.**

ScrapeGuard 0.1 is a Python library and CLI that records a successful extraction,
then checks selectors and output against that baseline. It runs locally with
Playwright Chromium. No AI provider, API key, or remote service is required.

## Quick start

Requires **Python 3.11+**. From this repository:

```sh
python3 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'
python -m playwright install chromium

scrapeguard baseline --config examples/scrapeguard.toml
scrapeguard check --config examples/scrapeguard.toml
```

The included example uses local HTML, so these commands require no website access.
The second command should report `PASS`. `python -m scrapeguard` also works.

Simulate a renamed selector:

```sh
cp examples/pages/renamed.html examples/pages/current.html
scrapeguard check -c examples/scrapeguard.toml
```

Expected finding (exit code 1):

```text
MISSING          price (.price)
  Selector matched no elements; inspect the page or review suggestions.
  Review candidate: [data-testid=current-price]
    Unique match with the same validated value and ancestor id/test marker
```

Simulate changed output, then restore the example:

```sh
cp examples/pages/changed.html examples/pages/current.html
scrapeguard check -c examples/scrapeguard.toml  # CHANGED: 59.9 -> 64.9; exit 1
cp examples/pages/original.html examples/pages/current.html
scrapeguard check -c examples/scrapeguard.toml  # PASS
```

ScrapeGuard never edits your scraper or configuration. Review a suggested selector
and update your config manually. After reviewing a legitimate change, refresh the
baseline explicitly:

```sh
scrapeguard baseline -c examples/scrapeguard.toml --force
```

## Configure your own scraper

Save `scrapeguard.toml`:

```toml
baseline = ".scrapeguard/baseline.json"

[[targets]]
name = "product"
url = "https://your-site.example/product"
wait_for = "#product"               # Optional readiness marker, attached to the DOM
timeout_ms = 10000                  # Navigation and readiness timeout
settle_ms = 0                       # Optional delay after readiness, in milliseconds

[[targets.fields]]
name = "title"
selector = "#product h1"
type = "text"

[[targets.fields]]
name = "price"
selector = "[data-testid='price']"
attribute = "data-price"            # Optional; otherwise extract textContent
type = "number"
track_changes = false              # Prices may change; count/type must still be valid

[[targets.fields]]
name = "details"
selector = "a.details"
attribute = "href"
type = "url"
```

Repeat `[[targets]]` and `[[targets.fields]]` as needed. Names must be unique within
their scope. Unknown options and invalid types are rejected to catch typos early.
URLs can be HTTP(S), `file://` URLs, or local HTML paths. Local paths and the
configured baseline path resolve **relative to the config file**, independent of
your working directory. `--baseline path` overrides that path relative to the
current working directory.

Each field must match **exactly one element**. v0.1 uses native CSS selectors in
the main document: XPath, Playwright text/role locators, frames, and shadow roots
are outside this release's scope. Hidden elements count as matches, and extraction
uses `textContent`, not rendered `innerText`. Put a stable `wait_for` on dynamic
pages; fields are inspected once after readiness, with no individual selector
retry that could hide a broken selector.

| Type | Valid output | Comparison |
| --- | --- | --- |
| `text` (default) | Non-empty text | Trimmed; whitespace collapsed |
| `integer` | Signed base-10 digits, e.g. `42`, `-3` | Parsed integer |
| `number` | Finite decimal/scientific number, e.g. `5.20`, `1e3` | Parsed float |
| `url` | Absolute HTTP(S) URL or relative URL resolving to HTTP(S) | Resolved against element `baseURI` |

Currency symbols and thousands separators are deliberately rejected. Use a clean
attribute such as `data-price`, or monitor formatted prices as `text`. Number
comparison uses Python floats, so it is not suitable for detecting differences
beyond floating-point precision. Use `text` for exact decimal strings. Missing
attributes and empty values are invalid data.

`track_changes` defaults to `true`. A legitimate data update still reports
`changed`; this is a review signal, not a claim that the scraper is broken. Set it
to `false` for naturally changing fields while retaining selector/type checks.

## Reports and baseline behavior

```sh
scrapeguard check --json > report.json
scrapeguard baseline --headed
scrapeguard --version
```

Human-readable and JSON reports include the target, selector, match count,
status, current/previous values, and any review candidates. JSON has
`schema_version = 1`; configuration/setup errors also produce JSON with `--json`.

| Exit code | Meaning |
| --- | --- |
| `0` | Every target/field passed; baseline saved when capturing |
| `1` | Monitoring findings: missing/ambiguous/invalid selector, invalid or changed data, page failure |
| `2` | Configuration, baseline, browser setup, or storage error |
| `130` | Interrupted by the user |

Baselines include normalized values, an element tag and selected attributes,
up to 1,000 characters of element HTML, up to 512 characters of element text, and
three ancestors with up to 300 characters of text each. Extracted values themselves
are retained in full. Files are versioned and bound to a fingerprint of the target
configuration; changing a URL, selector, type, or readiness setting requires a
reviewed refresh. Baseline paths do not affect the fingerprint.

Capture saves only when **all fields on all targets pass**. Existing baselines
require `--force`; failed refreshes preserve the old baseline. Successful writes
are atomic, and checks do not modify the baseline. Each standalone target gets a
fresh browser context; HTTP errors and navigation/readiness failures are reported
without preventing inspection of subsequent targets.

Snapshots and reports may contain sensitive page content. They remain local and
`.scrapeguard/` is gitignored. Choose the monitored fields and storage location
accordingly.

## Conservative selector suggestions

When a selector is missing or ambiguous, ScrapeGuard can propose CSS candidates
using a test marker, ID, name, item property, or class. A candidate must:

1. Match exactly one element in the current document.
2. Extract the same validated value as the baseline.
3. Share an ancestor ID or test marker from the baseline's nearby context.
4. Be the only eligible element under these checks.

It abstains when there is no reliable ancestor marker, values differ, several
elements qualify, or the page has over 1,000 candidate elements. Up to three
selectors may be reported for the **same** element. These checks provide evidence
for review; they cannot prove semantic identity. There are no confidence
percentages and no automatic patch application.

## Use inside an existing Playwright scraper

The inspection API accepts an already loaded synchronous Playwright `Page`, so
your scraper can manage login, navigation, interactions, and readiness itself:

```python
from pathlib import Path
from playwright.sync_api import sync_playwright
from scrapeguard import (
    Config,
    FieldConfig,
    Report,
    TargetConfig,
    baseline_from_report,
    inspect_page,
    load_baseline,
    save_baseline,
)

target = TargetConfig(
    name="product",
    url="https://your-site.example/product",
    fields=(FieldConfig("title", "h1", type="text"),),
)
config = Config((target,), Path(".scrapeguard/library.json"))

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(target.url)
    page.locator("h1").wait_for()

    if not config.baseline_path.exists():
        capture = Report([inspect_page(page, target)], mode="baseline")
        save_baseline(config.baseline_path, baseline_from_report(config, capture))

    baseline = load_baseline(config.baseline_path, config)
    result = inspect_page(page, target, baseline.targets[target.name])
    for field in result.fields:
        print(field.name, field.status, field.value, field.suggestions)
    browser.close()
```

`inspect_page` does not navigate, wait, write files, or modify the page. Use
`load_config`, `run`, and the storage helpers for the same complete workflow as
the CLI. v0.1 is synchronous; async support is on the roadmap.

## Development

```sh
python -m pytest
ruff check .
ruff format --check .
python -m build
```

Tests use deterministic local HTML and a temporary local HTTP server. They run
in real Chromium; missing browser installations fail tests rather than skipping
them. The suite exercises DOM drift, type/value validation, suggestion refusal,
baseline persistence, dynamic-page readiness, HTTP errors, and actual CLI
subprocesses. GitHub Actions runs these checks for Python 3.11 and 3.13.

The small package separates configuration, data types, validation, page inspection,
browser running, baseline storage, and CLI reporting. Contributions should include
a reproducible fixture and a test for changes to detection or suggestion behavior.

See [ROADMAP.md](ROADMAP.md) for opt-in Gemini, OpenAI, and Ollama healing.
Licensed under [MIT](LICENSE).

Implementation references: [Playwright Page API](https://playwright.dev/python/docs/api/class-page),
[Playwright browser installation](https://playwright.dev/python/docs/browsers), and
[Python packaging guide](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).
