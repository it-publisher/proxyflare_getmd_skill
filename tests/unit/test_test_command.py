import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from proxyflare.cli.app import app
from proxyflare.cli.exceptions import WorkerError

runner = CliRunner()

TARGET = "https://target.test/ip"


def make_workers_file(path, *urls):
    records = [
        {"name": f"worker-{i}", "url": url, "type": "js", "created_at": 1.0, "key": f"key-{i}"}
        for i, url in enumerate(urls)
    ]
    path.write_text(json.dumps(records))
    return path


def run_test_command(workers_file, *extra_args):
    return runner.invoke(
        app, ["test", "--workers-file", str(workers_file), "--url", TARGET, *extra_args]
    )


@pytest.fixture
def two_workers(tmp_path):
    return make_workers_file(tmp_path / "w.json", "https://w0.test", "https://w1.test")


@respx.mock
def test_each_worker_gets_one_request_with_its_own_key(two_workers):
    first = respx.get("https://w0.test").mock(return_value=httpx.Response(200, text="ok"))
    second = respx.get("https://w1.test").mock(return_value=httpx.Response(200, text="ok"))

    result = run_test_command(two_workers)

    assert result.exit_code == 0
    assert "Loaded 2 workers" in result.stdout
    assert "Test complete" in result.stdout
    assert first.calls.last.request.headers["X-Proxyflare-Key"] == "key-0"
    assert second.calls.last.request.headers["X-Proxyflare-Key"] == "key-1"
    assert first.calls.last.request.url.params["url"] == TARGET


@respx.mock
def test_limit_cycles_through_workers(two_workers):
    first = respx.get("https://w0.test").mock(return_value=httpx.Response(200))
    second = respx.get("https://w1.test").mock(return_value=httpx.Response(200))

    result = run_test_command(two_workers, "--limit", "3")

    assert result.exit_code == 0
    assert "Request 3/3" in result.stdout
    assert first.call_count == 2
    assert second.call_count == 1


@respx.mock
def test_error_status_makes_the_command_fail(two_workers):
    respx.get("https://w0.test").mock(return_value=httpx.Response(200))
    respx.get("https://w1.test").mock(return_value=httpx.Response(401))

    result = run_test_command(two_workers)

    assert result.exit_code == 1
    assert isinstance(result.exception, WorkerError)
    assert "1 of 2 test requests failed" in str(result.exception)
    assert "Test complete" not in result.stdout


@respx.mock
@pytest.mark.parametrize(
    "error", [httpx.ConnectError("down"), httpx.ReadTimeout("slow")], ids=["connect", "timeout"]
)
def test_network_error_makes_the_command_fail(tmp_path, error):
    workers_file = make_workers_file(tmp_path / "w.json", "https://w0.test")
    respx.get("https://w0.test").mock(side_effect=error)

    result = run_test_command(workers_file)

    assert result.exit_code == 1
    assert "1 of 1 test requests failed" in str(result.exception)


@respx.mock
def test_body_with_square_brackets_is_printed_as_is(tmp_path):
    """Rich would treat this as markup and raise an error."""
    workers_file = make_workers_file(tmp_path / "w.json", "https://w0.test")
    respx.get("https://w0.test").mock(return_value=httpx.Response(200, text="[/not-markup]"))

    result = run_test_command(workers_file)

    assert result.exit_code == 0
    assert "[/not-markup]" in result.stdout


def test_missing_workers_file_fails(tmp_path):
    assert run_test_command(tmp_path / "missing.json").exit_code == 1


def test_invalid_workers_file_fails(tmp_path):
    path = tmp_path / "w.json"
    path.write_text("not json")

    result = run_test_command(path)

    assert result.exit_code == 1
    assert isinstance(result.exception, WorkerError)


def test_workers_file_defaults_to_config_dir(isolated_config_dir):
    result = runner.invoke(app, ["test", "--url", TARGET])
    assert result.exit_code == 1
