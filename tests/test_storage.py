import json
from dataclasses import replace

import pytest

from scrapeguard import (
    Config,
    FieldConfig,
    Report,
    ScrapeGuardError,
    TargetConfig,
    baseline_from_report,
    inspect_page,
    load_baseline,
    save_baseline,
)


def captured(page, tmp_path):
    target = TargetConfig("quote", "https://example.com", (FieldConfig("price", "span", "number"),))
    config = Config((target,), tmp_path / "baseline.json")
    page.set_content('<section id="quote"><span>5.2</span></section>')
    report = Report([inspect_page(page, target)], "baseline")
    return config, baseline_from_report(config, report)


def test_round_trip_and_no_clobber(page, tmp_path):
    config, baseline = captured(page, tmp_path)
    save_baseline(config.baseline_path, baseline)
    before = config.baseline_path.read_bytes()
    assert load_baseline(config.baseline_path, config) == baseline
    with pytest.raises(ScrapeGuardError, match="exists"):
        save_baseline(config.baseline_path, baseline)
    assert config.baseline_path.read_bytes() == before
    updated = replace(baseline, created_at="2026-10-10T00:00:00+00:00")
    save_baseline(config.baseline_path, updated, overwrite=True)
    assert load_baseline(config.baseline_path, config) == updated
    assert not list(tmp_path.glob(".baseline-*"))


def test_bad_capture_cannot_replace_baseline(page, tmp_path):
    config, baseline = captured(page, tmp_path)
    save_baseline(config.baseline_path, baseline)
    page.set_content("<p>No price</p>")
    report = Report([inspect_page(page, config.targets[0])], "baseline")
    with pytest.raises(ScrapeGuardError, match="every field"):
        baseline_from_report(config, report)
    assert load_baseline(config.baseline_path, config) == baseline


def test_config_mismatch_is_explicit(page, tmp_path):
    config, baseline = captured(page, tmp_path)
    save_baseline(config.baseline_path, baseline)
    changed_target = replace(config.targets[0], url="https://example.com/new")
    with pytest.raises(ScrapeGuardError, match="Config differs"):
        load_baseline(config.baseline_path, replace(config, targets=(changed_target,)))


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(schema_version=99),
        lambda p: p.update(schema_version=True),
        lambda p: p.update(targets={}),
        lambda p: p.update(created_at=123),
        lambda p: p["targets"]["quote"].update(price={"value": 5.2, "context": {}}),
        lambda p: p["targets"]["quote"]["price"].update(value="5.2"),
        lambda p: p["targets"]["quote"]["price"].update(value=float("nan")),
        lambda p: p["targets"]["quote"]["price"]["context"].update(parents=[None]),
    ],
)
def test_corrupt_baseline_has_no_traceback(page, tmp_path, change):
    config, baseline = captured(page, tmp_path)
    save_baseline(config.baseline_path, baseline)
    payload = json.loads(config.baseline_path.read_text())
    change(payload)
    config.baseline_path.write_text(json.dumps(payload))
    with pytest.raises(ScrapeGuardError):
        load_baseline(config.baseline_path, config)


def test_missing_and_invalid_json(tmp_path):
    config = Config((), tmp_path / "baseline.json")
    with pytest.raises(ScrapeGuardError, match="baseline first"):
        load_baseline(config.baseline_path, config)
    config.baseline_path.write_text("bad json")
    with pytest.raises(ScrapeGuardError, match="Cannot read"):
        load_baseline(config.baseline_path, config)
