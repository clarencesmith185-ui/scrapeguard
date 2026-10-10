"""Strict TOML configuration with paths relative to the config file."""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlparse

from .models import FieldConfig, ScrapeGuardError, TargetConfig


@dataclass(frozen=True)
class Config:
    targets: tuple[TargetConfig, ...]
    baseline_path: Path

    @property
    def fingerprint(self) -> str:
        payload = json.dumps([asdict(t) for t in self.targets], sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


def _keys(data: dict, allowed: set[str], label: str) -> None:
    unknown = data.keys() - allowed
    if unknown:
        raise ScrapeGuardError(f"{label}: unknown option(s): {', '.join(sorted(unknown))}")


def load_config(path: str | Path) -> Config:
    path = Path(path).resolve()
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise ScrapeGuardError(f"Cannot read config {path}: {exc}") from exc
    _keys(data, {"baseline", "targets"}, "config")
    baseline = data.get("baseline", ".scrapeguard/baseline.json")
    if not isinstance(baseline, str) or not baseline.strip():
        raise ScrapeGuardError("baseline must be a non-empty path string")
    items = data.get("targets")
    if not isinstance(items, list) or not items:
        raise ScrapeGuardError("config must contain at least one [[targets]] entry")
    targets = []
    for item in items:
        if not isinstance(item, dict):
            raise ScrapeGuardError("each target must be a TOML table")
        _keys(item, {"name", "url", "fields", "wait_for", "timeout_ms", "settle_ms"}, "target")
        fields = item.get("fields")
        if not isinstance(fields, list) or not fields:
            raise ScrapeGuardError("each target must contain [[targets.fields]] entries")
        parsed = []
        for entry in fields:
            if not isinstance(entry, dict):
                raise ScrapeGuardError("each field must be a TOML table")
            _keys(entry, {"name", "selector", "type", "attribute", "track_changes"}, "field")
            if not {"name", "selector"} <= entry.keys():
                raise ScrapeGuardError("each field needs name and selector")
            parsed.append(FieldConfig(**entry))
        if not {"name", "url"} <= item.keys():
            raise ScrapeGuardError("each target needs name and url")
        url = item["url"]
        if not isinstance(url, str) or not url.strip():
            raise ScrapeGuardError("target url must be a non-empty string")
        try:
            parsed_url = urlparse(url)
        except ValueError as exc:
            raise ScrapeGuardError(f"Invalid target URL {url!r}: {exc}") from exc
        scheme = parsed_url.scheme
        if not scheme:
            url = (path.parent / url).resolve().as_uri()
        elif scheme not in ("http", "https", "file"):
            raise ScrapeGuardError("target URL must use http, https, file, or a local path")
        elif scheme in ("http", "https") and not parsed_url.netloc:
            raise ScrapeGuardError(f"target URL has no host: {url}")
        options = {k: v for k, v in item.items() if k not in ("url", "fields")}
        targets.append(TargetConfig(url=url, fields=tuple(parsed), **options))
    if len({t.name for t in targets}) != len(targets):
        raise ScrapeGuardError("duplicate target names")
    return Config(tuple(targets), (path.parent / baseline).resolve())
