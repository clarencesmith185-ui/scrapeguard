import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from scrapeguard import load_config, run
from scrapeguard.cli import main


def configure(tmp_path, fixtures):
    page = tmp_path / "page.html"
    page.write_text((fixtures / "original.html").read_text())
    config = tmp_path / "scrapeguard.toml"
    config.write_text("""
[[targets]]
name = "quote"
url = "page.html"
[[targets.fields]]
name = "price"
selector = ".price"
type = "number"
""")
    return config, page, tmp_path / ".scrapeguard" / "baseline.json"


def cli(config, *args):
    return subprocess.run(
        [sys.executable, "-m", "scrapeguard", *args, "--config", str(config)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_complete_cli_workflow(tmp_path, fixtures):
    config, page, baseline = configure(tmp_path, fixtures)
    capture = cli(config, "baseline", "--json")
    assert capture.returncode == 0, capture.stderr
    assert json.loads(capture.stdout)["baseline_path"] == str(baseline)
    initial = baseline.read_bytes()
    assert cli(config, "check").returncode == 0
    duplicate = cli(config, "baseline")
    assert duplicate.returncode == 2
    assert "--force" in duplicate.stderr
    page.write_text((fixtures / "renamed.html").read_text())
    missing = cli(config, "check", "--json")
    assert missing.returncode == 1, missing.stderr
    finding = json.loads(missing.stdout)["targets"][0]["fields"][0]
    assert finding["status"] == "missing"
    assert finding["suggestions"][0]["selector"] == "[data-testid=current-price]"
    failed_refresh = cli(config, "baseline", "--force")
    assert failed_refresh.returncode == 1
    assert baseline.read_bytes() == initial
    page.write_text((fixtures / "original.html").read_text().replace("5.20", "6.50"))
    changed = cli(config, "check")
    assert changed.returncode == 1
    assert "CHANGED" in changed.stdout and "baseline: 5.2" in changed.stdout
    assert baseline.read_bytes() == initial
    assert cli(config, "baseline", "--force").returncode == 0
    assert cli(config, "check").returncode == 0


def test_missing_baseline_json_error(tmp_path, fixtures):
    config, _, _ = configure(tmp_path, fixtures)
    result = cli(config, "check", "--json")
    assert result.returncode == 2
    assert "baseline first" in json.loads(result.stdout)["error"]
    assert not result.stderr


def test_config_error_json(tmp_path, capsys):
    config = tmp_path / "bad.toml"
    config.write_text("unknown = true")
    assert main(["check", "--config", str(config), "--json"]) == 2
    assert "unknown option" in json.loads(capsys.readouterr().out)["error"]


def test_invalid_selector_report_does_not_save_baseline(tmp_path, fixtures):
    config, _, baseline = configure(tmp_path, fixtures)
    config.write_text(config.read_text().replace('selector = ".price"', 'selector = "["'))
    result = cli(config, "baseline", "--json")
    assert result.returncode == 1
    assert json.loads(result.stdout)["targets"][0]["fields"][0]["status"] == "invalid_selector"
    assert not baseline.exists()


@pytest.fixture
def http_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(503 if self.path == "/bad" else 200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h1>ready</h1><script>setTimeout(() => { "
                b'const p = document.createElement("span"); '
                b'p.id="ready"; p.textContent="5.20"; '
                b"document.body.appendChild(p); }, 100)</script>"
            )

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_runner_waits_and_continues_after_http_failure(tmp_path, http_server):
    path = tmp_path / "config.toml"
    path.write_text(f'''
[[targets]]
name = "bad"
url = "{http_server}/bad"
[[targets.fields]]
name = "price"
selector = "#ready"
[[targets]]
name = "good"
url = "{http_server}/good"
wait_for = "#ready"
timeout_ms = 2000
[[targets.fields]]
name = "price"
selector = "#ready"
type = "number"
''')
    report = run(load_config(path))
    assert not report.ok
    assert "HTTP 503" in report.targets[0].error
    assert report.targets[1].ok and report.targets[1].fields[0].value == 5.2


def test_runner_readiness_timeout_is_actionable(tmp_path, fixtures):
    config, _, _ = configure(tmp_path, fixtures)
    config.write_text(
        config.read_text().replace(
            'url = "page.html"', 'url = "page.html"\nwait_for = "#absent"\ntimeout_ms = 100'
        )
    )
    report = run(load_config(config))
    assert not report.ok
    assert "Navigation/readiness failed" in report.targets[0].error
