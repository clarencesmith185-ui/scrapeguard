import pytest

from scrapeguard import FieldConfig, ScrapeGuardError, TargetConfig, load_config

VALID = """
[[targets]]
name = "quote"
url = "page.html"
[[targets.fields]]
name = "price"
selector = ".price"
type = "number"
"""


def test_relative_paths_and_defaults(tmp_path, monkeypatch):
    path = tmp_path / "scrapeguard.toml"
    path.write_text(VALID)
    monkeypatch.chdir(tmp_path.parent)
    config = load_config(path)
    assert config.targets[0].url == (tmp_path / "page.html").as_uri()
    assert config.baseline_path == tmp_path / ".scrapeguard/baseline.json"
    assert config.targets[0].fields[0].track_changes
    assert config.fingerprint == load_config(path).fingerprint


@pytest.mark.parametrize(
    "text",
    [
        "",
        "targets = []",
        "unknown = true\n" + VALID,
        VALID.replace('type = "number"', 'type = "money"'),
        VALID.replace('type = "number"', 'track_changes = "no"'),
        VALID.replace('selector = ".price"', 'selector = ""'),
        VALID.replace('selector = ".price"', 'selectorr = ".price"'),
        VALID.replace('url = "page.html"', 'url = "javascript:alert(1)"'),
        VALID.replace('url = "page.html"', 'url = "https:///page"'),
        VALID.replace('url = "page.html"', 'url = "https://[bad"'),
        VALID.replace('url = "page.html"', 'url = "page.html"\ntimeout_ms = true'),
        VALID.replace('url = "page.html"', 'url = "page.html"\nsettle_ms = -1'),
        VALID + '\n[[targets.fields]]\nname = "price"\nselector = "#price"',
        VALID + VALID,
        '[[targets]]\nname = "x"\nurl = "page.html"',
        "[bad toml",
    ],
)
def test_invalid_configuration_has_actionable_error(tmp_path, text):
    path = tmp_path / "bad.toml"
    path.write_text(text)
    with pytest.raises(ScrapeGuardError):
        load_config(path)


def test_library_configs_validate():
    with pytest.raises(ScrapeGuardError):
        FieldConfig("x", "h1", track_changes="no")
    with pytest.raises(ScrapeGuardError):
        TargetConfig("x", "https://example.com", ())
