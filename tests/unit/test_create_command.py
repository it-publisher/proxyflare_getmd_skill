import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from proxyflare.cli.app import app
from proxyflare.cli.exceptions import ConfigError, WorkerError
from proxyflare.exceptions import SubdomainMissingError

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
    assert "reach all Cloudflare locations" in " ".join(result.stdout.split())

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

    assert result.exit_code == 1
    assert "1 of 2 workers failed" in str(result.exception)
    data = json.loads(result_path.read_text())
    assert len(data) == 1
    assert data[0]["name"] == "proxyflare-1-ok"


def test_create_all_deploys_failed(mock_ctx):
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"

    ctx.service.get_worker_source.return_value = ("source", None)
    ctx.service.generate_worker_name.return_value = "proxyflare-1-fail"
    ctx.service.deploy_worker.side_effect = RuntimeError("Deploy failed")

    result = runner.invoke(app, ["create", "--result", str(result_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, WorkerError)
    assert not result_path.exists()


def test_create_keeps_workers_from_earlier_runs(mock_ctx):
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"

    ctx.service.get_worker_source.return_value = ("source", None)
    ctx.service.generate_worker_name.side_effect = ["proxyflare-1-aaa", "proxyflare-2-bbb"]
    ctx.service.deploy_worker.side_effect = ["https://a.dev", "https://b.dev"]

    assert runner.invoke(app, ["create", "--result", str(result_path)]).exit_code == 0
    assert runner.invoke(app, ["create", "--result", str(result_path)]).exit_code == 0

    data = json.loads(result_path.read_text())
    assert [worker["name"] for worker in data] == ["proxyflare-1-aaa", "proxyflare-2-bbb"]
    assert data[0]["key"] != data[1]["key"]


def test_create_refuses_to_deploy_when_workers_file_is_invalid(mock_ctx):
    """New workers would be left unrecorded, and the old file's contents lost."""
    ctx, tmp_path = mock_ctx
    result_path = tmp_path / "result.json"
    result_path.write_text('[{"name": "old-worker", "key": "old-secret"}]')

    result = runner.invoke(app, ["create", "--result", str(result_path)])

    assert result.exit_code == 1
    assert isinstance(result.exception, ConfigError)
    assert "old-secret" not in str(result.exception)
    ctx.service.deploy_worker.assert_not_called()
    assert "old-worker" in result_path.read_text()


def test_create_saves_to_config_dir_by_default(mock_ctx, isolated_config_dir):
    ctx, _ = mock_ctx

    ctx.service.get_worker_source.return_value = ("source", None)
    ctx.service.generate_worker_name.return_value = "proxyflare-1-aaa"
    ctx.service.deploy_worker.return_value = "https://a.dev"

    assert runner.invoke(app, ["create"]).exit_code == 0

    workers_file = isolated_config_dir / "workers.json"
    assert json.loads(workers_file.read_text())[0]["name"] == "proxyflare-1-aaa"
    assert workers_file.stat().st_mode & 0o777 == 0o600
    assert isolated_config_dir.stat().st_mode & 0o777 == 0o700


def test_create_rejects_zero_count(mock_ctx):
    ctx, _ = mock_ctx
    assert runner.invoke(app, ["create", "--count", "0"]).exit_code == 2
    ctx.service.deploy_worker.assert_not_called()


def test_create_reports_missing_subdomain_with_its_own_message(mock_ctx):
    ctx, tmp_path = mock_ctx
    ctx.service.get_worker_source.return_value = ("source", None)
    ctx.service.ensure_subdomain.side_effect = SubdomainMissingError("Set up a subdomain")

    result = runner.invoke(app, ["create", "--result", str(tmp_path / "result.json")])

    assert result.exit_code == 1
    assert isinstance(result.exception, SubdomainMissingError)


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
