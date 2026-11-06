import io
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from proxyflare.cli.app import app

runner = CliRunner()


@pytest.fixture
def workers_file(tmp_path):
    """Create a temporary workers JSON file."""
    workers_data = [
        {
            "name": "proxyflare-test-1",
            "url": "https://proxyflare-test-1.example.workers.dev",
            "type": "js",
            "created_at": 1700000000.0,
            "key": "test-key",
        }
    ]
    filepath = tmp_path / "workers.json"
    filepath.write_text(json.dumps(workers_data))
    return filepath


# --- Happy path ---


def test_test_workers_success(workers_file):
    """Test command loads workers and makes a request."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.json.return_value = {"origin": "1.2.3.4"}
    mock_response.text = '{"origin": "1.2.3.4"}'

    with patch("proxyflare.cli.commands.test.ProxyflareTransport"):
        with patch("proxyflare.cli.commands.test.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            MockClient.return_value = mock_client

            result = runner.invoke(app, ["test", "--workers-file", str(workers_file)])

    assert result.exit_code == 0
    assert "Loaded 1 workers" in result.stdout
    assert "Test complete" in result.stdout


# --- Error cases ---


def test_test_workers_file_not_found():
    """Missing workers file should exit with hint."""
    buf = io.StringIO()
    # Patch err_console in the console module so it's picked up by the app
    with patch("proxyflare.cli.console.err_console", Console(file=buf)):
        result = runner.invoke(app, ["test", "--workers-file", "/nonexistent/workers.json"])

    assert result.exit_code == 1
    output = buf.getvalue()
    assert "not found" in output.lower() or "Error" in output


def test_test_workers_multiple_requests(workers_file):
    """Test multiple requests with --limit."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.is_success = True
    mock_response.json.return_value = {"origin": "1.2.3.4"}

    with patch("proxyflare.cli.commands.test.ProxyflareTransport"):
        with patch("proxyflare.cli.commands.test.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.get.return_value = mock_response
            MockClient.return_value = mock_client

            result = runner.invoke(
                app, ["test", "--workers-file", str(workers_file), "--limit", "3"]
            )

    assert result.exit_code == 0
    assert "Request 3/3" in result.stdout
    assert "Test complete" in result.stdout
