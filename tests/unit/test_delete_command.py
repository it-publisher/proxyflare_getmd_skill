import io
import json
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console
from typer.testing import CliRunner

from proxyflare.cli.app import app

runner = CliRunner()


def strip_ansi(text: str) -> str:
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


@pytest.fixture
def mock_ctx():
    """Mock create_app_context to return a fake AppContext."""
    mock_service = MagicMock()
    mock_service.delete_worker = AsyncMock()
    mock_service.list_workers = AsyncMock()
    mock_service.worker_prefix = "proxyflare"

    mock_config = MagicMock()
    mock_config.api_token.get_secret_value.return_value = "test-token"
    mock_config.account_id = "test-account-id"
    mock_config.worker_prefix = "proxyflare"

    mock_app_ctx = MagicMock()
    mock_app_ctx.config = mock_config
    mock_app_ctx.service = mock_service
    # Provide real Console instances writing to stdout (captured by CliRunner)
    mock_app_ctx.console = Console()
    mock_app_ctx.err_console = Console()

    # Mock the async context manager
    mock_cm = MagicMock()
    mock_cm.__aenter__.return_value = mock_app_ctx
    mock_cm.__aexit__.return_value = None

    with patch("proxyflare.cli.commands.delete.get_app_context", return_value=mock_cm):
        yield mock_app_ctx


def test_delete_worker_success(mock_ctx):
    result = runner.invoke(app, ["delete", "proxyflare-test-worker"], input="y\n")

    assert result.exit_code == 0
    assert "Successfully deleted worker: proxyflare-test-worker" in result.stdout
    mock_ctx.service.delete_worker.assert_called_once_with("proxyflare-test-worker")


def test_delete_worker_cancelled(mock_ctx):
    result = runner.invoke(app, ["delete", "proxyflare-test-worker"], input="n\n")

    assert result.exit_code == 0  # Cancelled usually means clean exit
    mock_ctx.service.delete_worker.assert_not_called()


def test_delete_worker_force(mock_ctx):
    result = runner.invoke(app, ["delete", "--force", "proxyflare-test-worker"])

    assert result.exit_code == 0
    mock_ctx.service.delete_worker.assert_called_once_with("proxyflare-test-worker")


def test_delete_worker_error(mock_ctx):
    mock_ctx.service.delete_worker.side_effect = ValueError("Denied")

    result = runner.invoke(app, ["delete", "--force", "proxyflare-test-worker"])

    assert result.exit_code == 1
    # Check that the exception is WorkerError (or raised from it)
    assert "Denied" in str(result.exception)


# --- delete --all tests ---


def test_delete_no_args():
    """Must error if neither name nor --all is provided."""
    mock_cm = MagicMock()
    mock_cm.__aenter__.return_value = MagicMock()
    mock_cm.__aexit__.return_value = None

    buf = io.StringIO()
    with patch("proxyflare.cli.commands.delete.get_app_context", return_value=mock_cm):
        # Patch the console imported in delete.py
        with patch(
            "proxyflare.cli.commands.delete.err_console", Console(file=buf, force_terminal=True)
        ):
            result = runner.invoke(app, ["delete"])
    assert result.exit_code == 1


def test_delete_name_and_all_conflict(mock_ctx):
    """Must error if both name and --all are provided."""
    result = runner.invoke(app, ["delete", "--all", "--force", "proxyflare-test-worker"])
    assert result.exit_code == 1


def test_delete_all_success(mock_ctx):
    """--all should list workers and delete each one."""
    mock_ctx.service.list_workers.return_value = [
        {"id": "proxyflare-1"},
        {"id": "proxyflare-2"},
    ]

    result = runner.invoke(app, ["delete", "--all", "--force"])

    assert result.exit_code == 0
    assert mock_ctx.service.delete_worker.call_count == 2
    assert "Deleted 2 worker(s)" in result.stdout


def test_delete_all_empty(mock_ctx):
    """--all with no workers should show a warning."""
    mock_ctx.service.list_workers.return_value = []

    result = runner.invoke(app, ["delete", "--all", "--force"])

    assert result.exit_code == 0
    assert "No workers found" in result.stdout
    mock_ctx.service.delete_worker.assert_not_called()


def test_delete_all_cancelled(mock_ctx):
    """--all without --force should ask for confirmation; 'n' cancels."""
    mock_ctx.service.list_workers.return_value = [
        {"id": "proxyflare-1"},
    ]

    # Patch err_console to capture "Deletion cancelled"
    with patch("proxyflare.cli.commands.delete.err_console", Console()):
        result = runner.invoke(app, ["delete", "--all"], input="n\n")

    assert result.exit_code == 0  # Cancelled usually means clean exit
    mock_ctx.service.delete_worker.assert_not_called()


def make_workers_file(path, *names):
    path.write_text(
        json.dumps(
            [
                {
                    "name": name,
                    "url": f"https://{name}.dev",
                    "type": "js",
                    "created_at": 1.0,
                    "key": "k",
                }
                for name in names
            ]
        )
    )
    return path


def saved_names(path):
    return [worker["name"] for worker in json.loads(path.read_text())]


def test_delete_removes_worker_from_file(mock_ctx, tmp_path):
    path = make_workers_file(tmp_path / "w.json", "proxyflare-1", "proxyflare-2")

    args = ["delete", "--force", "proxyflare-1", "--workers-file", str(path)]
    assert runner.invoke(app, args).exit_code == 0

    assert saved_names(path) == ["proxyflare-2"]


def test_delete_uses_workers_file_in_config_dir_by_default(mock_ctx, isolated_config_dir):
    isolated_config_dir.mkdir()
    path = make_workers_file(isolated_config_dir / "workers.json", "proxyflare-1")

    assert runner.invoke(app, ["delete", "--force", "proxyflare-1"]).exit_code == 0

    assert saved_names(path) == []


def test_delete_keeps_worker_in_file_when_api_fails(mock_ctx, tmp_path):
    path = make_workers_file(tmp_path / "w.json", "proxyflare-1")
    mock_ctx.service.delete_worker.side_effect = RuntimeError("API Error")

    args = ["delete", "--force", "proxyflare-1", "--workers-file", str(path)]
    assert runner.invoke(app, args).exit_code == 1

    assert saved_names(path) == ["proxyflare-1"]


def test_delete_all_keeps_failed_workers_in_file(mock_ctx, tmp_path):
    path = make_workers_file(tmp_path / "w.json", "proxyflare-ok", "proxyflare-fail", "other")
    mock_ctx.service.list_workers.return_value = [
        {"id": "proxyflare-ok"},
        {"id": "proxyflare-fail"},
    ]
    mock_ctx.service.delete_worker.side_effect = [None, RuntimeError("API Error")]

    args = ["delete", "--all", "--force", "--workers-file", str(path)]
    assert runner.invoke(app, args).exit_code == 1

    assert saved_names(path) == ["proxyflare-fail", "other"]


def test_delete_succeeds_when_workers_file_is_invalid(mock_ctx, tmp_path):
    """The worker is gone from Cloudflare, so a broken local file is only a warning."""
    path = tmp_path / "w.json"
    path.write_text("not json")

    args = ["delete", "--force", "proxyflare-1", "--workers-file", str(path)]
    assert runner.invoke(app, args).exit_code == 0

    assert path.read_text() == "not json"


def test_delete_all_partial_failure(mock_ctx):
    """If some deletions fail, report both succeeded and failed counts."""
    mock_ctx.service.list_workers.return_value = [
        {"id": "proxyflare-ok"},
        {"id": "proxyflare-fail"},
    ]
    # Since delete --all calls list_workers twice, we ensure robust return

    mock_ctx.service.delete_worker.side_effect = [
        None,  # first succeeds
        RuntimeError("API Error"),  # second fails
    ]

    buf = io.StringIO()
    c = Console(file=buf, force_terminal=True)
    with (
        patch("proxyflare.cli.commands.delete.console", c),
        patch("proxyflare.cli.commands.delete.err_console", c),
        patch("proxyflare.cli.console.err_console", c),
    ):
        result = runner.invoke(app, ["delete", "--all", "--force"])

    assert result.exit_code == 1
    assert "Failed to delete 1 worker(s)" in str(result.exception)
    output = strip_ansi(buf.getvalue())
    assert "Deleted 1 worker(s)" in output
    assert "Failed to delete proxyflare-fail" in output
