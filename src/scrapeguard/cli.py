"""CLI entry point. Monitoring findings exit 1; setup/configuration errors exit 2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import load_config
from .models import Report, ScrapeGuardError
from .runner import run
from .storage import baseline_from_report, load_baseline, save_baseline


def _print_report(report: Report, *, json_output: bool, saved_path: Path | None) -> None:
    if json_output:
        payload = report.to_dict()
        if saved_path is not None:
            payload["baseline_path"] = str(saved_path)
        print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        return
    print(f"ScrapeGuard {report.mode}: {'PASS' if report.ok else 'ISSUES FOUND'}")
    for target in report.targets:
        print(f"\n{target.name} — {target.url}")
        if target.error:
            print(f"  PAGE_ERROR: {target.error}")
        for field in target.fields:
            print(f"  {field.status.upper():<16} {field.name} ({field.selector})")
            print(f"    {field.message}")
            if field.value is not None:
                print(f"    value: {field.value!r}")
            if field.status == "changed":
                print(f"    baseline: {field.previous_value!r}")
            for suggestion in field.suggestions:
                print(f"    Review candidate: {suggestion.selector}\n      {suggestion.reason}")
    if saved_path:
        print(f"\nBaseline saved: {saved_path}")
    elif report.mode == "baseline" and not report.ok:
        print("\nBaseline not saved; fix all issues and retry.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scrapeguard", description="Monitor CSS selectors and scraper output with Playwright."
    )
    parser.add_argument("--version", action="version", version=f"ScrapeGuard {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("baseline", "Capture validated element snapshots"),
        ("check", "Compare the current page against the baseline"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("-c", "--config", default="scrapeguard.toml", help="TOML config path")
        command.add_argument(
            "--baseline", type=Path, help="Override baseline path (relative to cwd)"
        )
        command.add_argument("--json", action="store_true", dest="json_output", help="JSON report")
        command.add_argument("--headed", action="store_true", help="Show Chromium browser")
        if name == "baseline":
            command.add_argument(
                "--force", action="store_true", help="Replace an existing baseline"
            )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        path = args.baseline.resolve() if args.baseline else config.baseline_path
        if args.command == "baseline" and path.exists() and not args.force:
            raise ScrapeGuardError(
                f"Baseline exists at {path}; use baseline --force to replace it."
            )
        baseline = load_baseline(path, config) if args.command == "check" else None
        report = run(config, baseline, headed=args.headed)
        saved_path = None
        if args.command == "baseline" and report.ok:
            save_baseline(path, baseline_from_report(config, report), overwrite=args.force)
            saved_path = path
        _print_report(report, json_output=args.json_output, saved_path=saved_path)
        return 0 if report.ok else 1
    except ScrapeGuardError as exc:
        if args.json_output:
            print(json.dumps({"schema_version": 1, "ok": False, "error": str(exc)}))
        else:
            print(f"ScrapeGuard error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("ScrapeGuard interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
