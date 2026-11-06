from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from proxyflare.cli.commands.config import config_app

runner = CliRunner()


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.config.account_id = "test-account"
    ctx.config.api_token.get_secret_value.return_value = "test-token"
    # Ensure subdomain is async
    ctx.service.ensure_subdomain = AsyncMock(return_value="test-sub")
    return ctx


def test_verify_command_success(mock_ctx):
    """Test the verify command with successful API response and all permissions."""
    with (
        patch("proxyflare.cli.commands.config.get_app_context") as mock_get_ctx,
        patch("cloudflare.Client") as MockClient,
        patch("proxyflare.validation.verify_token") as mock_verify_token,
        patch("proxyflare.validation.check_token_permissions") as mock_check_permissions,
        patch("shutil.which", return_value="/usr/bin/wrangler"),
    ):
        mock_get_ctx.return_value.__aenter__.return_value = mock_ctx

        # Mock successful token verification
        mock_verify_token.return_value = "test_token_id"

        result = runner.invoke(config_app, ["verify"])

    assert result.exit_code == 0
    assert "Wrangler/Npx found:" in result.stdout
    assert "VALID (id: test_token_id)" in result.stdout
    assert "Token has all required permissions." in result.stdout
    assert "Checking Workers Subdomain... FOUND" in result.stdout

    # Verify strict client usage
    MockClient.assert_called_once_with(api_token="test-token")  # noqa: S106
    mock_verify_token.assert_called_once()
    mock_check_permissions.assert_called_once()


def test_verify_command_verification_errors(mock_ctx):
    """Test verify command with verification errors."""
    with (
        patch("proxyflare.cli.commands.config.get_app_context") as mock_get_ctx,
        patch("cloudflare.Client"),
        patch("proxyflare.validation.verify_token") as mock_verify_token,
        patch("proxyflare.validation.check_token_permissions"),
        patch("shutil.which", return_value="/usr/bin/wrangler"),
    ):
        mock_get_ctx.return_value.__aenter__.return_value = mock_ctx

        # Mock verification failure
        mock_verify_token.side_effect = Exception("Token inactive")

        # Mock functional check failure
        mock_ctx.service.ensure_subdomain.side_effect = Exception("Subdomain Error")

        result = runner.invoke(config_app, ["verify"])

    # Should raise ConfigError eventually
    assert result.exit_code == 1
    assert "Verify failed: Token inactive" in result.stdout
    assert "Verification failed" in str(result.exception) or "Token verification failed" in str(
        result.exception
    )


def test_verify_command_missing_permissions(mock_ctx):
    """Test the verify command when permissions are missing but subdomain check passes."""
    with (
        patch("proxyflare.cli.commands.config.get_app_context") as mock_get_ctx,
        patch("cloudflare.Client"),
        patch("proxyflare.validation.verify_token") as mock_verify_token,
        patch("proxyflare.validation.check_token_permissions") as mock_check_permissions,
        patch("shutil.which", return_value="/usr/bin/wrangler"),
    ):
        mock_get_ctx.return_value.__aenter__.return_value = mock_ctx

        # Successful token verify
        mock_verify_token.return_value = "test_token_id"

        # Check permissions fails
        mock_check_permissions.side_effect = ValueError(
            "Missing required permissions: {'Workers Scripts Write'}"
        )

        result = runner.invoke(config_app, ["verify"])

    # Warns but does not fail if functional check passes
    assert result.exit_code == 0
    assert "Missing required permissions" in result.stdout
    assert "FOUND" in result.stdout


def test_show_command():
    """Test the show command."""
    with patch("proxyflare.cli.commands.config.Config") as MockConfig:
        mock_config_instance = MagicMock()
        mock_config_instance.__str__.return_value = "Mock Config"
        MockConfig.load.return_value = mock_config_instance

        result = runner.invoke(config_app, ["show"])

        assert result.exit_code == 0
        assert "Mock Config" in result.stdout
        assert "Workers file:" in result.stdout
