import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from proxyflare.cli.app import app
from proxyflare.cli.exceptions import ConfigError, WorkerError

runner = CliRunner()


def strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


@pytest.fixture
def mock_ctx(tmp_path):
    """Mock create_app_context to return a fake AppContext."""
    mock_service = MagicMock()
    # Async methods must be AsyncMock for asyncio.run() / await
    mock_service.ensure_subdomain = AsyncMock()
    mock_service.deploy_worker = AsyncMock()
    mock_service.list_workers = AsyncMock()
    mock_service.delete_worker = AsyncMock()

    mock_config = MagicMock()
    mock_config.api_token.get_secret_value.return_value = "test-token"
    mock_config.account_id = "test-account-id"
    mock_config.worker_prefix = "proxyflare"
    mock_config.worker_type = "js"

    mock_app_ctx = MagicMock()
    mock_app_ctx.config = mock_config
    mock_app_ctx.service = mock_service
    mock_app_ctx.console = Console()
    mock_app_ctx.err_console = Console()

    # Mock the async context manager
    mock_cm = MagicMock()
    mock_cm.__aenter__.return_value = mock_app_ctx
    mock_cm.__aexit__.return_value = None

    with patch("proxyflare.cli.commands.create.get_app_context", return_value=mock_cm):
        yield mock_app_ctx, tmp_path


# --- Happy path ---


def test_create_single_worker(mock_ctx):
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"

    ctx.service.get_worker_source.return_value = ("print('hello')", None)
    ctx.service.ensure_subdomain.return_value = "test-sub"
    ctx.service.generate_worker_name.return_value = "proxyflare-123-abc"
    ctx.service.deploy_worker.return_value = "https://proxyflare-123-abc.test-sub.workers.dev"

    result = runner.invoke(app, ["create", "--result", str(result_path)])

    assert result.exit_code == 0
    assert "Successfully created 1 workers" in result.stdout

    # Verify JSON result
    data = json.loads(result_path.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "proxyflare-123-abc"
    assert data[0]["url"] == "https://proxyflare-123-abc.test-sub.workers.dev"
    assert data[0]["type"] == "js"

    deployed_config = ctx.service.deploy_worker.call_args.args[0]
    assert len(data[0]["key"]) >= 32
    assert deployed_config.key == data[0]["key"]

    ctx.service.deploy_worker.assert_called_once()


def test_create_multiple_workers(mock_ctx):
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"

    ctx.service.get_worker_source.return_value = ("print('hello')", None)
    ctx.service.ensure_subdomain.return_value = "test-sub"

    names = ["proxyflare-1-aaa", "proxyflare-2-bbb", "proxyflare-3-ccc"]
    ctx.service.generate_worker_name.side_effect = names
    ctx.service.deploy_worker.side_effect = [f"https://{n}.test-sub.workers.dev" for n in names]

    result = runner.invoke(app, ["create", "--count", "3", "--result", str(result_path)])

    assert result.exit_code == 0
    assert "Successfully created 3 workers" in result.stdout
    data = json.loads(result_path.read_text())
    assert len(data) == 3


# --- Error cases ---


def test_create_invalid_worker_type(mock_ctx):
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"

    result = runner.invoke(app, ["create", "--type", "go", "--result", str(result_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, ConfigError)
    assert "Invalid worker type" in str(result.exception)


def test_create_source_not_found(mock_ctx):
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"

    ctx.service.get_worker_source.side_effect = FileNotFoundError("JS worker not found")

    result = runner.invoke(app, ["create", "--result", str(result_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, WorkerError)
    assert "not found" in str(result.exception).lower()


def test_create_subdomain_error(mock_ctx):
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"

    ctx.service.get_worker_source.return_value = ("print('hello')", None)
    ctx.service.ensure_subdomain.side_effect = RuntimeError("subdomain is not configured")

    result = runner.invoke(app, ["create", "--result", str(result_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, WorkerError)
    assert "subdomain is not configured" in str(result.exception)


def test_create_partial_deploy_failure(mock_ctx):
    """One worker fails to deploy, others succeed — should still save partial results."""
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"

    ctx.service.get_worker_source.return_value = ("print('hello')", None)
    ctx.service.ensure_subdomain.return_value = "test-sub"

    names = ["proxyflare-1-ok", "proxyflare-2-fail"]
    ctx.service.generate_worker_name.side_effect = names
    ctx.service.deploy_worker.side_effect = [
        "https://proxyflare-1-ok.test-sub.workers.dev",
        RuntimeError("Deploy failed"),
    ]

    result = runner.invoke(app, ["create", "--count", "2", "--result", str(result_path)])

    assert result.exit_code == 0  # Partial success
    data = json.loads(result_path.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "proxyflare-1-ok"


def test_create_with_explicit_type(mock_ctx):
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"

    ctx.service.get_worker_source.return_value = ("addEventListener('fetch'..)", None)
    ctx.service.ensure_subdomain.return_value = "test-sub"
    ctx.service.generate_worker_name.return_value = "proxyflare-js-abc"
    ctx.service.deploy_worker.return_value = "https://proxyflare-js-abc.test-sub.workers.dev"

    result = runner.invoke(app, ["create", "--type", "js", "--result", str(result_path)])

    assert result.exit_code == 0
    data = json.loads(result_path.read_text())
    assert data[0]["type"] == "js"
    ctx.service.get_worker_source.assert_called_once_with("js")
