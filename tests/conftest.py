import pytest
from pydantic import SecretStr

from proxyflare.models.config import Config


@pytest.fixture
def mock_config():
    """Fixture that returns a Config object with dummy values."""
    return Config(
        account_id="test_account_id",
        api_token=SecretStr("test_api_token"),
    )
