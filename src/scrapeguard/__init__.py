"""ScrapeGuard's synchronous Playwright monitoring API."""

__version__ = "0.1.0"

from .config import Config, load_config
from .engine import inspect_page
from .models import FieldConfig, Report, ScrapeGuardError, Snapshot, TargetConfig
from .runner import run
from .storage import Baseline, baseline_from_report, load_baseline, save_baseline

__all__ = [
    "Baseline",
    "Config",
    "FieldConfig",
    "Report",
    "ScrapeGuardError",
    "Snapshot",
    "TargetConfig",
    "baseline_from_report",
    "inspect_page",
    "load_baseline",
    "load_config",
    "run",
    "save_baseline",
]
