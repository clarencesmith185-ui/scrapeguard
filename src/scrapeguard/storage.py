"""Versioned, config-bound baseline persistence with atomic writes."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .models import Report, ScrapeGuardError, Snapshot


@dataclass(frozen=True)
class Baseline:
    created_at: str
    fingerprint: str
    targets: dict[str, dict[str, Snapshot]]


def baseline_from_report(config: Config, report: Report) -> Baseline:
    if not report.ok:
        raise ScrapeGuardError("Baseline was not saved: every field must pass validation.")
    expected = {t.name: {f.name for f in t.fields} for t in config.targets}
    actual = {t.name: {f.name for f in t.fields} for t in report.targets}
    if expected != actual:
        raise ScrapeGuardError("Report targets/fields do not match configuration.")
    targets = {}
    for target in report.targets:
        targets[target.name] = {}
        for field in target.fields:
            if field.value is None or field.context is None:
                raise ScrapeGuardError("Report contains an incomplete observation.")
            targets[target.name][field.name] = Snapshot(field.value, field.context)
    return Baseline(datetime.now(UTC).isoformat(), config.fingerprint, targets)


def save_baseline(path: str | Path, baseline: Baseline, *, overwrite: bool = False) -> None:
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".baseline-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(
                {"schema_version": 1, **asdict(baseline)},
                stream,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            # Atomic no-clobber creation even if two captures run concurrently.
            os.link(temporary, path)
    except FileExistsError as exc:
        raise ScrapeGuardError(
            f"Baseline exists at {path}; use baseline --force to replace it."
        ) from exc
    except (OSError, ValueError) as exc:
        raise ScrapeGuardError(f"Cannot save baseline {path}: {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _valid_context(context: object) -> bool:
    if not isinstance(context, dict):
        return False
    if not all(isinstance(context.get(k), str) for k in ("tag", "text", "html")):
        return False
    parents = context.get("parents")
    if not isinstance(parents, list):
        return False
    for node in [context, *parents]:
        if not isinstance(node, dict) or not isinstance(node.get("tag"), str):
            return False
        if not isinstance(node.get("text"), str):
            return False
        attrs = node.get("attributes")
        if not isinstance(attrs, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in attrs.items()
        ):
            return False
    return True


def load_baseline(path: str | Path, config: Config) -> Baseline:
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScrapeGuardError(f"No baseline at {path}; run scrapeguard baseline first.") from exc
    except (OSError, UnicodeError, ValueError) as exc:
        raise ScrapeGuardError(f"Cannot read baseline {path}: {exc}") from exc
    if not isinstance(payload, dict) or type(payload.get("schema_version")) is not int:
        raise ScrapeGuardError("Malformed baseline; create a new baseline with --force.")
    if payload["schema_version"] != 1:
        raise ScrapeGuardError("Unsupported baseline version; create a new baseline with --force.")
    if payload.get("fingerprint") != config.fingerprint:
        raise ScrapeGuardError(
            "Config differs from baseline; review changes then baseline --force."
        )
    try:
        if not isinstance(payload["created_at"], str):
            raise ValueError("invalid timestamp")
        datetime.fromisoformat(payload["created_at"])
        items = payload["targets"]
        if not isinstance(items, dict) or set(items) != {t.name for t in config.targets}:
            raise ValueError("target names differ")
        targets = {}
        for target in config.targets:
            fields = items[target.name]
            if not isinstance(fields, dict) or set(fields) != {f.name for f in target.fields}:
                raise ValueError("field names differ")
            targets[target.name] = {}
            for field in target.fields:
                snapshot = fields[field.name]
                if not isinstance(snapshot, dict) or not _valid_context(snapshot.get("context")):
                    raise ValueError("invalid element context")
                value = snapshot["value"]
                expected_type = {"text": str, "url": str, "integer": int, "number": float}
                if type(value) is not expected_type[field.type]:
                    raise ValueError("invalid stored value type")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("non-finite stored number")
                targets[target.name][field.name] = Snapshot(value, snapshot["context"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ScrapeGuardError(f"Malformed baseline: {exc}; recreate it with --force.") from exc
    return Baseline(payload["created_at"], payload["fingerprint"], targets)
