import pytest
from pydantic import SecretStr

from proxyflare.models.config import Config
from proxyflare.paths import CONFIG_DIR_ENV


@pytest.fixture(autouse=True)
def isolated_config_dir(tmp_path, monkeypatch):
    """Keep tests away from the real files of whoever runs them."""
    monkeypatch.setenv(CONFIG_DIR_ENV, str(tmp_path / "config"))
    return tmp_path / "config"


@pytest.fixture
def mock_config():
    """Fixture that returns a Config object with dummy values."""
    return Config(
        account_id="test_account_id",
        api_token=SecretStr("test_api_token"),
    )
