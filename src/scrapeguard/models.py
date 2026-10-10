"""Small public data types shared by the library and CLI."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

OutputType = Literal["text", "integer", "number", "url"]


class ScrapeGuardError(Exception):
    """An actionable configuration, baseline, or browser setup error."""


@dataclass(frozen=True)
class FieldConfig:
    name: str
    selector: str
    type: OutputType = "text"
    attribute: str | None = None
    track_changes: bool = True

    def __post_init__(self) -> None:
        for name in ("name", "selector"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ScrapeGuardError(f"field {name} must be a non-empty string")
        if self.type not in ("text", "integer", "number", "url"):
            raise ScrapeGuardError(f"field {self.name!r}: unknown output type {self.type!r}")
        if self.attribute is not None and (
            not isinstance(self.attribute, str) or not self.attribute.strip()
        ):
            raise ScrapeGuardError(f"field {self.name!r}: attribute must be a non-empty string")
        if not isinstance(self.track_changes, bool):
            raise ScrapeGuardError(f"field {self.name!r}: track_changes must be a boolean")


@dataclass(frozen=True)
class TargetConfig:
    name: str
    url: str
    fields: tuple[FieldConfig, ...]
    wait_for: str | None = None
    timeout_ms: int = 10_000
    settle_ms: int = 0

    def __post_init__(self) -> None:
        for name in ("name", "url"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ScrapeGuardError(f"target {name} must be a non-empty string")
        if not self.fields or not all(isinstance(f, FieldConfig) for f in self.fields):
            raise ScrapeGuardError(f"target {self.name!r}: fields must contain FieldConfig objects")
        if len({f.name for f in self.fields}) != len(self.fields):
            raise ScrapeGuardError(f"target {self.name!r}: duplicate field names")
        if self.wait_for is not None and (
            not isinstance(self.wait_for, str) or not self.wait_for.strip()
        ):
            raise ScrapeGuardError(f"target {self.name!r}: wait_for must be a non-empty string")
        for name, minimum in (("timeout_ms", 1), ("settle_ms", 0)):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ScrapeGuardError(f"target {self.name!r}: {name} must be >= {minimum}")


@dataclass(frozen=True)
class Snapshot:
    value: str | int | float
    context: dict[str, Any]


@dataclass(frozen=True)
class Suggestion:
    selector: str
    reason: str


@dataclass
class FieldResult:
    name: str
    selector: str
    status: str
    message: str
    match_count: int | None = None
    value: str | int | float | None = None
    previous_value: str | int | float | None = None
    context: dict[str, Any] | None = None
    suggestions: list[Suggestion] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "ok"


@dataclass
class TargetResult:
    name: str
    url: str
    fields: list[FieldResult] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and all(f.ok for f in self.fields)


@dataclass
class Report:
    targets: list[TargetResult]
    mode: str

    @property
    def ok(self) -> bool:
        return all(t.ok for t in self.targets)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "mode": self.mode, "ok": self.ok, **asdict(self)}
