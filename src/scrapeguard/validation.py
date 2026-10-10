"""Normalize extraction results and validate their declared type."""

import math
import re
from urllib.parse import urljoin, urlparse

from .models import OutputType


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def parse_value(raw: str | None, expected: OutputType, base_url: str) -> str | int | float:
    if raw is None:
        raise ValueError("configured attribute is absent")
    text = normalize_text(raw)
    if not text:
        raise ValueError("extracted value is empty")
    if expected == "text":
        return text
    if expected == "integer":
        if not re.fullmatch(r"[+-]?[0-9]+", text):
            raise ValueError(f"expected integer, got {text!r}")
        try:
            return int(text)
        except ValueError as exc:
            raise ValueError("integer exceeds supported length") from exc
    if expected == "number":
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text):
            raise ValueError(f"expected number, got {text!r}")
        value = float(text)
        if not math.isfinite(value):
            raise ValueError("number must be finite")
        return value
    if expected == "url":
        value = urljoin(base_url, text)
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError(f"expected HTTP(S) URL, got {text!r}")
        if re.search(r"\s", value):
            raise ValueError("URL must not contain whitespace")
        return value
    raise ValueError(f"unknown output type: {expected}")
