import pytest
from pydantic import ValidationError

from proxyflare.models.config import Config


def test_config_from_env(monkeypatch):
    """Test loading configuration from environment variables."""
    monkeypatch.setenv("PROXYFLARE_ACCOUNT_ID", "env_account")
    monkeypatch.setenv("PROXYFLARE_API_TOKEN", "env_token")

    config = Config(_env_file=None)  # type: ignore[call-arg]
    assert config.account_id == "env_account"
    assert config.api_token.get_secret_value() == "env_token"


def test_config_missing_env(monkeypatch):
    """Test that Config raises ValidationError if required vars are missing."""
    monkeypatch.delenv("PROXYFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("PROXYFLARE_API_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        Config(_env_file=None)  # type: ignore[call-arg]


def test_load_reads_env_file_from_config_dir(monkeypatch, isolated_config_dir):
    monkeypatch.delenv("PROXYFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("PROXYFLARE_API_TOKEN", raising=False)
    isolated_config_dir.mkdir()
    (isolated_config_dir / ".env").write_text(
        "PROXYFLARE_ACCOUNT_ID=file_account\nPROXYFLARE_API_TOKEN=file_token\n"
    )

    config = Config.load()

    assert config.account_id == "file_account"
    assert config.api_token.get_secret_value() == "file_token"


def test_load_ignores_env_file_in_current_directory(monkeypatch, tmp_path):
    """Otherwise a project's own .env would silently change which account gets deployed to."""
    monkeypatch.delenv("PROXYFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("PROXYFLARE_API_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        "PROXYFLARE_ACCOUNT_ID=local_account\nPROXYFLARE_API_TOKEN=local_token\n"
    )
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValidationError):
        Config.load()


def test_environment_wins_over_env_file(monkeypatch, isolated_config_dir):
    isolated_config_dir.mkdir()
    (isolated_config_dir / ".env").write_text(
        "PROXYFLARE_ACCOUNT_ID=file_account\nPROXYFLARE_API_TOKEN=file_token\n"
    )
    monkeypatch.setenv("PROXYFLARE_ACCOUNT_ID", "env_account")

    assert Config.load().account_id == "env_account"
